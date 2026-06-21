"""Tests for owa_tui.screens.sched.SchedScreen.

Covers:
  - _parse_grid: column label derivation, cell decoding, error row
  - _next_workday: always returns a Mon-Fri date
  - _DIGIT_STATUS and _CELL_STYLE mappings
  - SchedScreen.__init__ defaults and config overrides
  - SchedScreen.cell_style all branches
  - SchedScreen.menu_config
  - SchedScreen.fetch_grid with fixture short-circuit (Textual pilot)
  - SchedScreen.fetch_grid empty payload path
  - Live fetch path: api_post mocked → grid populated (Textual pilot)
  - Cursor movement (j/k/h/l) does not crash
  - r refresh re-runs fetch_grid
  - Esc opens menu overlay (Resume visible)
  - q quits the screen

All async helpers are wrapped in asyncio.run() — no pytest-asyncio needed
(project convention mirrors test_grid_screen.py).
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header

from owa_tui.screens.sched import (
    _CELL_STYLE,
    _DEMO_ATTENDEES,
    _DIGIT_STATUS,
    SchedScreen,
    _next_workday,
    _parse_grid,
)
from owa_tui.widgets.status_bar import StatusBar

# ---------------------------------------------------------------------------
# Fixture data (mirrors e2e/fixtures/sched.json structure)
# ---------------------------------------------------------------------------

_FIXTURE_VALUE: dict = {
    "value": [
        {
            "scheduleId": "alice@contoso.com",
            "availabilityView": "002120000",
            "scheduleItems": [
                {
                    "status": "busy",
                    "start": {"dateTime": "2026-06-23T09:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-06-23T10:00:00.0000000", "timeZone": "UTC"},
                    "subject": "Standup",
                },
                {
                    "status": "tentative",
                    "start": {"dateTime": "2026-06-23T11:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-06-23T12:00:00.0000000", "timeZone": "UTC"},
                    "subject": "1:1",
                },
            ],
            "workingHours": {},
        },
        {
            "scheduleId": "bob@contoso.com",
            "availabilityView": "000000200",
            "scheduleItems": [
                {
                    "status": "busy",
                    "start": {"dateTime": "2026-06-23T15:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-06-23T16:00:00.0000000", "timeZone": "UTC"},
                    "subject": "Review",
                },
            ],
            "workingHours": {},
        },
    ]
}

_FIXTURE_WITH_ERROR: dict = {
    "value": [
        {
            "scheduleId": "alice@contoso.com",
            "availabilityView": "002120000",
            "scheduleItems": [],
            "workingHours": {},
        },
        {
            "scheduleId": "bad@contoso.com",
            "availabilityView": "",
            "error": {"message": "Mailbox not found"},
            "scheduleItems": [],
            "workingHours": {},
        },
    ]
}


# ---------------------------------------------------------------------------
# Test app wrapper
# ---------------------------------------------------------------------------


def _make_app(**screen_kw: Any) -> App:
    class _TestApp(App):
        TITLE = "sched-test"

        def compose(self) -> ComposeResult:
            yield Header()

        def on_mount(self) -> None:
            self.push_screen(SchedScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Unit tests: pure helpers
# ---------------------------------------------------------------------------


class TestNextWorkday:
    def test_returns_weekday(self) -> None:
        d = date.fromisoformat(_next_workday())
        assert d.weekday() < 5  # 0=Mon … 4=Fri

    def test_is_after_today(self) -> None:
        d = date.fromisoformat(_next_workday())
        assert d > date.today()

    def test_skips_weekend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Simulate today = Friday → next workday must be Monday
        friday = date(2026, 6, 19)
        monkeypatch.setattr(
            "owa_tui.screens.sched.date",
            type("FakeDate", (), {"today": staticmethod(lambda: friday)}),
        )
        result = _next_workday()
        d = date.fromisoformat(result)
        assert d.weekday() == 0  # Monday


class TestParseGrid:
    def test_empty_value_returns_empty(self) -> None:
        cols, rows = _parse_grid({"value": []})
        assert cols == []
        assert rows == []

    def test_empty_dict_returns_empty(self) -> None:
        cols, rows = _parse_grid({})
        assert cols == []
        assert rows == []

    def test_column_count_matches_av_length(self) -> None:
        cols, rows = _parse_grid(_FIXTURE_VALUE)
        # alice has 9 chars in availabilityView
        assert len(cols) == 9

    def test_column_labels_are_hhmm(self) -> None:
        cols, _ = _parse_grid(_FIXTURE_VALUE)
        for label in cols:
            h, m = label.split(":")
            assert 0 <= int(h) < 24
            assert int(m) in (0, 30)

    def test_row_count_matches_attendees(self) -> None:
        _, rows = _parse_grid(_FIXTURE_VALUE)
        assert len(rows) == 2

    def test_row_labels_are_emails(self) -> None:
        _, rows = _parse_grid(_FIXTURE_VALUE)
        emails = [r[0] for r in rows]
        assert "alice@contoso.com" in emails
        assert "bob@contoso.com" in emails

    def test_cell_decoding_busy(self) -> None:
        _, rows = _parse_grid(_FIXTURE_VALUE)
        # alice's av = "002120000" → slot 2 = "busy"
        alice_cells = rows[0][1]
        assert alice_cells[2] == "busy"

    def test_cell_decoding_tentative(self) -> None:
        _, rows = _parse_grid(_FIXTURE_VALUE)
        # alice's av = "002120000" → slot 3 = "tentative" (digit "1")
        alice_cells = rows[0][1]
        assert alice_cells[3] == "tentative"

    def test_cell_decoding_free(self) -> None:
        _, rows = _parse_grid(_FIXTURE_VALUE)
        # alice's slot 0 = "0" = "free"
        alice_cells = rows[0][1]
        assert alice_cells[0] == "free"

    def test_error_row_all_error_cells(self) -> None:
        _, rows = _parse_grid(_FIXTURE_WITH_ERROR)
        # alice is normal, bad is error
        bad_cells = rows[1][1]
        assert all(c == "error" for c in bad_cells)

    def test_zero_length_av_on_first_entry_returns_empty(self) -> None:
        raw = {"value": [{"scheduleId": "a@b.com", "availabilityView": ""}]}
        cols, rows = _parse_grid(raw)
        assert cols == []
        assert rows == []


class TestDigitStatusMapping:
    def test_all_five_digits_mapped(self) -> None:
        assert _DIGIT_STATUS["0"] == "free"
        assert _DIGIT_STATUS["1"] == "tentative"
        assert _DIGIT_STATUS["2"] == "busy"
        assert _DIGIT_STATUS["3"] == "oof"
        assert _DIGIT_STATUS["4"] == "workingElsewhere"


class TestCellStyleMapping:
    def test_known_statuses_have_styles(self) -> None:
        for status in ("free", "busy", "tentative", "oof", "workingElsewhere", "error"):
            assert _CELL_STYLE[status]


# ---------------------------------------------------------------------------
# Unit tests: SchedScreen (no Textual app)
# ---------------------------------------------------------------------------


class TestSchedScreenInit:
    def test_defaults(self) -> None:
        screen = SchedScreen()
        assert screen._tool_name == "sched"
        assert screen._audience == "graph"
        assert screen._screen_title == "Scheduling"
        assert screen._attendees == _DEMO_ATTENDEES
        assert screen._work_start == "08:00"
        assert screen._work_end == "17:00"

    def test_config_overrides_work_hours(self) -> None:
        cfg = {"default_work_start": "09:00", "default_work_end": "18:00"}
        screen = SchedScreen(config=cfg)
        assert screen._work_start == "09:00"
        assert screen._work_end == "18:00"

    def test_custom_attendees(self) -> None:
        attendees = ["x@example.com", "y@example.com"]
        screen = SchedScreen(attendees=attendees)
        assert screen._attendees == attendees


class TestCellStyle:
    def setup_method(self) -> None:
        self.screen = SchedScreen()

    def test_free_returns_green(self) -> None:
        assert self.screen.cell_style("alice@x.com", "08:00", "free") == "green"

    def test_busy_returns_red(self) -> None:
        assert self.screen.cell_style("alice@x.com", "09:00", "busy") == "red"

    def test_tentative_returns_yellow(self) -> None:
        assert self.screen.cell_style("alice@x.com", "10:00", "tentative") == "yellow"

    def test_oof_returns_dark_orange(self) -> None:
        assert self.screen.cell_style("alice@x.com", "11:00", "oof") == "dark_orange"

    def test_working_elsewhere_returns_cyan(self) -> None:
        assert self.screen.cell_style("alice@x.com", "12:00", "workingElsewhere") == "cyan"

    def test_error_returns_dim_red(self) -> None:
        assert self.screen.cell_style("bad@x.com", "08:00", "error") == "dim red"

    def test_unknown_returns_dim(self) -> None:
        assert self.screen.cell_style("x@y.com", "08:00", "unknown") == "dim"

    def test_unrecognized_value_returns_none(self) -> None:
        assert self.screen.cell_style("x@y.com", "08:00", "NotAStatus") is None


class TestMenuConfig:
    def test_menu_config_title(self) -> None:
        screen = SchedScreen()
        title, fields = screen.menu_config()
        assert "Scheduling" in title
        assert isinstance(fields, list)
        assert fields == []


# ---------------------------------------------------------------------------
# Pilot tests: Textual app integration
# ---------------------------------------------------------------------------


def test_grid_renders_from_fixture() -> None:
    """Fixture short-circuit: grid populates from sched.json data."""

    async def _run() -> tuple[int, int]:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                tbl = app.screen.query_one("#owa-grid-table", DataTable)
                return tbl.row_count, len(list(tbl.columns))

    rows, cols = asyncio.run(_run())
    # 2 attendees → 2 rows; 9 slots + 1 row-label column = 10 columns
    assert rows == 2
    assert cols == 10


def test_status_bar_shows_row_count_after_fixture_load() -> None:
    """Status bar message includes row and column counts."""

    async def _run() -> str:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                return app.screen._status

    status = asyncio.run(_run())
    assert "rows" in status
    assert "columns" in status


def test_empty_payload_sets_no_data_status() -> None:
    """When payload is empty, status should be '(no data)'."""

    async def _run() -> str:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value={"value": []}):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                return app.screen._status

    status = asyncio.run(_run())
    assert status == "(no data)"


def test_cursor_movement_does_not_crash() -> None:
    """j/k/h/l keys navigate without raising."""

    async def _run() -> str:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                for key in ("j", "k", "h", "l", "j", "k", "h", "l"):
                    await pilot.press(key)
                    await pilot.pause(0.05)
                return app.screen._status

    status = asyncio.run(_run())
    assert not status.startswith("error:")


def test_r_key_triggers_refresh() -> None:
    """Pressing r re-runs fetch_grid (fetch_calls count increases)."""

    async def _run() -> int:
        class _CountingSchedScreen(SchedScreen):
            fetch_calls: int = 0

            async def fetch_grid(self, search: str = "") -> Any:
                self.fetch_calls += 1
                return _parse_grid(_FIXTURE_VALUE)

        class _App(App):
            def compose(self) -> ComposeResult:
                yield Header()

            def on_mount(self) -> None:
                self.push_screen(_CountingSchedScreen())

        app = _App()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.4)
            await pilot.press("r")
            await pilot.pause(0.4)
            return app.screen.fetch_calls

    calls = asyncio.run(_run())
    assert calls == 2


def test_escape_opens_menu_with_resume() -> None:
    """Esc key opens the SettingsOverlay which contains 'Resume'."""

    async def _run() -> bool:
        from owa_tui.widgets.settings_overlay import SettingsOverlay

        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                await pilot.press("escape")
                await pilot.pause(0.2)
                overlays = list(app.screen_stack)
                return any(isinstance(s, SettingsOverlay) for s in overlays)

    has_overlay = asyncio.run(_run())
    assert has_overlay


def test_q_quits_screen() -> None:
    """Pressing q pops the sched screen."""

    async def _run() -> bool:
        pop_called: list[bool] = []
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                # Patch pop_screen to record the call
                original_pop = app.pop_screen

                def _pop():
                    pop_called.append(True)
                    return original_pop()

                app.pop_screen = _pop  # type: ignore[method-assign]
                await pilot.press("q")
                await pilot.pause(0.1)
        return bool(pop_called)

    called = asyncio.run(_run())
    assert called


def test_live_fetch_via_mocked_api_post() -> None:
    """Live path: api_post returns a getSchedule value → grid populated."""

    async def _run() -> tuple[int, int]:
        app = _make_app(attendees=["alice@contoso.com", "bob@contoso.com"])
        # Fixture disabled; api_post returns the same fixture data
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch(
                "owa_tui.adapter.access_token_for",
                return_value="fake-token",
            ),
            patch(
                "owa_sched.api.api_post",
                return_value=_FIXTURE_VALUE,
            ),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.5)
                tbl = app.screen.query_one("#owa-grid-table", DataTable)
                return tbl.row_count, len(list(tbl.columns))

    rows, cols = asyncio.run(_run())
    assert rows == 2
    assert cols == 10


def test_live_fetch_none_payload_returns_no_data() -> None:
    """When api_post returns None (auth / network error), status shows error or no data."""

    async def _run() -> str:
        app = _make_app()
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="fake-token"),
            patch("owa_sched.api.api_post", return_value=None),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.5)
                return app.screen._status

    status = asyncio.run(_run())
    assert "(no data)" in status or "error" in status


def test_datatable_mounted() -> None:
    """DataTable widget is composed into the screen."""

    async def _run() -> int:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.1)
                return len(list(app.screen.query(DataTable)))

    count = asyncio.run(_run())
    assert count == 1


def test_status_bar_mounted() -> None:
    """StatusBar widget is composed into the screen."""

    async def _run() -> int:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.1)
                return len(list(app.screen.query(StatusBar)))

    count = asyncio.run(_run())
    assert count == 1


def test_error_row_styled_in_grid() -> None:
    """An attendee with a Graph error produces an 'error' cell in the grid."""
    cols, rows = _parse_grid(_FIXTURE_WITH_ERROR)
    bad_row = next(r for r in rows if r[0] == "bad@contoso.com")
    # All cells for the error row should be "error"
    assert all(cell == "error" for cell in bad_row[1])


# ---------------------------------------------------------------------------
# a — add-attendee prompt → append → re-fetch  [hardening]
# ---------------------------------------------------------------------------


def test_a_opens_prompt_and_appends_on_submit() -> None:
    """`a` pushes the add-attendee prompt; submitting appends + re-fetches."""
    from owa_tui.screens.base.screen import _SearchModal

    async def _run() -> tuple[int, list[str], bool]:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: SchedScreen = app.screen  # type: ignore[assignment]
            n0 = len(screen._attendees)
            await pilot.press("a")
            await pilot.pause(0.05)
            modal = app.screen
            is_prompt = isinstance(modal, _SearchModal)
            modal.dismiss("carol@contoso.com")  # type: ignore[union-attr]
            await pilot.pause(0.05)
            await app.workers.wait_for_complete()
            return n0, list(screen._attendees), is_prompt

    with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
        n0, attendees, is_prompt = asyncio.run(_run())
    assert is_prompt
    assert "carol@contoso.com" in attendees
    assert len(attendees) == n0 + 1


def test_a_cancel_does_not_append() -> None:
    """Cancelling the add-attendee prompt (empty result) appends nothing."""

    async def _run() -> tuple[int, list[str]]:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: SchedScreen = app.screen  # type: ignore[assignment]
            n0 = len(screen._attendees)
            await pilot.press("a")
            await pilot.pause(0.05)
            app.screen.dismiss(None)  # cancel  # type: ignore[union-attr]
            await pilot.pause(0.05)
            return n0, list(screen._attendees)

    with patch("owa_tui.fixtures.load", return_value=_FIXTURE_VALUE):
        n0, attendees = asyncio.run(_run())
    assert len(attendees) == n0
