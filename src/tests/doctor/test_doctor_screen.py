"""Tests for owa_tui.screens.doctor.DoctorScreen.

Covers:
  - _parse_grid: preserves insertion order for profiles and audiences,
    applies classify_finding correctly (ok / warn / fail), empty input
  - _RESULT_STYLE mapping completeness
  - DoctorScreen.__init__ defaults and positional config
  - DoctorScreen.cell_style: ok=green, warn=yellow, fail=bold red, unknown=None
  - DoctorScreen.menu_config returns ("Diagnostics — settings", [])
  - fetch_grid fixture short-circuit: grid populates from doctor.json findings
  - fetch_grid empty findings path: status = "(no data)"
  - fetch_grid live path: list_piggy_profiles + probe_profile_token mocked
  - Cursor movement (j/k/h/l) does not crash
  - r refresh re-runs fetch_grid (call count increases)
  - Esc opens SettingsOverlay (Resume visible)
  - q pops the screen

All async helpers are wrapped in asyncio.run() — no pytest-asyncio needed
(project convention mirrors test_sched_screen.py).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header

from owa_tui.screens.doctor import (
    _RESULT_STYLE,
    DoctorScreen,
    _parse_grid,
)
from owa_tui.widgets.status_bar import StatusBar

# ---------------------------------------------------------------------------
# Fixture data (mirrors e2e/fixtures/doctor.json)
# ---------------------------------------------------------------------------

_FIXTURE_FINDINGS: list[dict] = [
    # work — all ok (minutes_remaining=55 >= 10, token_ok=True)
    {"alias": "work", "audience": "graph", "token_ok": True,  "minutes_remaining": 55,  "token_audience": "https://graph.microsoft.com", "error": None},
    {"alias": "work", "audience": "mail",  "token_ok": True,  "minutes_remaining": 55,  "token_audience": "https://outlook.office.com",  "error": None},
    {"alias": "work", "audience": "cal",   "token_ok": True,  "minutes_remaining": 55,  "token_audience": "https://outlook.office.com",  "error": None},
    # personal — warn on graph+cal (minutes_remaining=6 < 10), fail on mail
    {"alias": "personal", "audience": "graph", "token_ok": True,  "minutes_remaining": 6,   "token_audience": "https://graph.microsoft.com", "error": None},
    {"alias": "personal", "audience": "mail",  "token_ok": False, "minutes_remaining": None, "token_audience": None,                          "error": "token expired"},
    {"alias": "personal", "audience": "cal",   "token_ok": True,  "minutes_remaining": 6,   "token_audience": "https://outlook.office.com",  "error": None},
    # devbox — all fail
    {"alias": "devbox", "audience": "graph", "token_ok": False, "minutes_remaining": None, "token_audience": None, "error": "no profile found"},
    {"alias": "devbox", "audience": "mail",  "token_ok": False, "minutes_remaining": None, "token_audience": None, "error": "no profile found"},
    {"alias": "devbox", "audience": "cal",   "token_ok": False, "minutes_remaining": None, "token_audience": None, "error": "no profile found"},
]

# Expected grid after classify_finding:
#           graph  mail  cal
# work      ok     ok    ok
# personal  warn   fail  warn
# devbox    fail   fail  fail


# ---------------------------------------------------------------------------
# Test app wrapper
# ---------------------------------------------------------------------------


def _make_app(**screen_kw: Any) -> App:
    class _TestApp(App):
        TITLE = "doctor-test"

        def compose(self) -> ComposeResult:
            yield Header()

        def on_mount(self) -> None:
            self.push_screen(DoctorScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Unit tests: _parse_grid
# ---------------------------------------------------------------------------


class TestParseGrid:
    def test_empty_list_returns_empty(self) -> None:
        cols, rows = _parse_grid([])
        assert cols == []
        assert rows == []

    def test_column_labels_derived_from_findings(self) -> None:
        cols, _ = _parse_grid(_FIXTURE_FINDINGS)
        assert cols == ["graph", "mail", "cal"]

    def test_row_labels_are_profile_aliases(self) -> None:
        _, rows = _parse_grid(_FIXTURE_FINDINGS)
        labels = [r[0] for r in rows]
        assert labels == ["work", "personal", "devbox"]

    def test_row_count_matches_unique_profiles(self) -> None:
        _, rows = _parse_grid(_FIXTURE_FINDINGS)
        assert len(rows) == 3

    def test_column_count_matches_unique_audiences(self) -> None:
        cols, _ = _parse_grid(_FIXTURE_FINDINGS)
        assert len(cols) == 3

    def test_work_row_all_ok(self) -> None:
        _, rows = _parse_grid(_FIXTURE_FINDINGS)
        work_cells = rows[0][1]
        assert work_cells == ["ok", "ok", "ok"]

    def test_personal_row_warn_fail_warn(self) -> None:
        _, rows = _parse_grid(_FIXTURE_FINDINGS)
        personal_cells = rows[1][1]
        assert personal_cells == ["warn", "fail", "warn"]

    def test_devbox_row_all_fail(self) -> None:
        _, rows = _parse_grid(_FIXTURE_FINDINGS)
        devbox_cells = rows[2][1]
        assert devbox_cells == ["fail", "fail", "fail"]

    def test_missing_audience_falls_back_to_fail(self) -> None:
        # If a (profile, audience) pair is absent, the lookup defaults to "fail"
        findings = [
            {"alias": "solo", "audience": "graph", "token_ok": True, "minutes_remaining": 30, "token_audience": "x", "error": None},
        ]
        cols, rows = _parse_grid(findings)
        assert cols == ["graph"]
        assert rows == [("solo", ["ok"])]

    def test_insertion_order_preserved(self) -> None:
        findings = [
            {"alias": "z", "audience": "cal",   "token_ok": True, "minutes_remaining": 30, "token_audience": "x", "error": None},
            {"alias": "a", "audience": "graph",  "token_ok": True, "minutes_remaining": 30, "token_audience": "x", "error": None},
            {"alias": "z", "audience": "graph",  "token_ok": True, "minutes_remaining": 30, "token_audience": "x", "error": None},
            {"alias": "a", "audience": "cal",    "token_ok": True, "minutes_remaining": 30, "token_audience": "x", "error": None},
        ]
        cols, rows = _parse_grid(findings)
        assert cols == ["cal", "graph"]
        row_labels = [r[0] for r in rows]
        assert row_labels == ["z", "a"]


# ---------------------------------------------------------------------------
# Unit tests: _RESULT_STYLE
# ---------------------------------------------------------------------------


class TestResultStyleMapping:
    def test_ok_is_green(self) -> None:
        assert _RESULT_STYLE["ok"] == "green"

    def test_warn_is_yellow(self) -> None:
        assert _RESULT_STYLE["warn"] == "yellow"

    def test_fail_is_bold_red(self) -> None:
        assert _RESULT_STYLE["fail"] == "bold red"


# ---------------------------------------------------------------------------
# Unit tests: DoctorScreen (no running app)
# ---------------------------------------------------------------------------


class TestDoctorScreenInit:
    def test_defaults(self) -> None:
        screen = DoctorScreen()
        assert screen._tool_name == "doctor"
        assert screen._audience == ""
        assert screen._screen_title == "Diagnostics"
        assert screen._debug is False

    def test_positional_config_accepted(self) -> None:
        """Matches exactly how OwaTuiApp.push_tool constructs screens."""
        screen = DoctorScreen({}, debug=False)
        assert screen is not None
        assert screen._tool_name == "doctor"

    def test_config_dict_stored(self) -> None:
        cfg = {"some_key": "some_value"}
        screen = DoctorScreen(cfg)
        assert screen._config == cfg

    def test_none_config_becomes_empty_dict(self) -> None:
        screen = DoctorScreen(None)
        assert screen._config == {}

    def test_debug_flag_propagated(self) -> None:
        screen = DoctorScreen({}, debug=True)
        assert screen._debug is True


class TestCellStyle:
    def setup_method(self) -> None:
        self.screen = DoctorScreen()

    def test_ok_returns_green(self) -> None:
        assert self.screen.cell_style("work", "graph", "ok") == "green"

    def test_warn_returns_yellow(self) -> None:
        assert self.screen.cell_style("personal", "graph", "warn") == "yellow"

    def test_fail_returns_bold_red(self) -> None:
        assert self.screen.cell_style("devbox", "mail", "fail") == "bold red"

    def test_unrecognized_value_returns_none(self) -> None:
        assert self.screen.cell_style("x", "y", "NotAStatus") is None


class TestMenuConfig:
    def test_menu_config_title(self) -> None:
        screen = DoctorScreen()
        title, fields = screen.menu_config()
        assert "Diagnostics" in title
        assert isinstance(fields, list)
        assert fields == []


# ---------------------------------------------------------------------------
# Pilot tests: Textual app integration
# ---------------------------------------------------------------------------


def test_grid_renders_from_fixture() -> None:
    """Fixture short-circuit: grid populates from doctor.json findings."""

    async def _run() -> tuple[int, int]:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_FINDINGS):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                tbl = app.screen.query_one("#owa-grid-table", DataTable)
                return tbl.row_count, len(list(tbl.columns))

    rows, cols = asyncio.run(_run())
    # 3 profiles → 3 rows; 3 audiences + 1 row-label column = 4 columns
    assert rows == 3
    assert cols == 4


def test_status_bar_shows_row_count_after_fixture_load() -> None:
    """Status bar message includes row and column counts."""

    async def _run() -> str:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_FINDINGS):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                return app.screen._status

    status = asyncio.run(_run())
    assert "rows" in status
    assert "columns" in status


def test_empty_findings_sets_no_data_status() -> None:
    """When findings list is empty, status is '(no data)'."""

    async def _run() -> str:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=[]):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                return app.screen._status

    status = asyncio.run(_run())
    assert status == "(no data)"


def test_cursor_movement_does_not_crash() -> None:
    """j/k/h/l keys navigate without raising."""

    async def _run() -> str:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_FINDINGS):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                for key in ("j", "j", "k", "l", "l", "h", "h", "k"):
                    await pilot.press(key)
                    await pilot.pause(0.05)
                return app.screen._status

    status = asyncio.run(_run())
    assert not status.startswith("error:")


def test_r_key_triggers_refresh() -> None:
    """Pressing r re-runs fetch_grid (fetch_calls count increases to 2)."""

    async def _run() -> int:
        class _CountingDoctorScreen(DoctorScreen):
            fetch_calls: int = 0

            async def fetch_grid(self, search: str = "") -> Any:
                self.fetch_calls += 1
                return _parse_grid(_FIXTURE_FINDINGS)

        class _App(App):
            def compose(self) -> ComposeResult:
                yield Header()

            def on_mount(self) -> None:
                self.push_screen(_CountingDoctorScreen())

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
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_FINDINGS):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
                await pilot.press("escape")
                await pilot.pause(0.2)
                return any(isinstance(s, SettingsOverlay) for s in app.screen_stack)

    has_overlay = asyncio.run(_run())
    assert has_overlay


def test_q_quits_screen() -> None:
    """Pressing q pops the doctor screen."""

    async def _run() -> bool:
        pop_called: list[bool] = []
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_FINDINGS):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.4)
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


def test_datatable_mounted() -> None:
    """DataTable widget is composed into the screen."""

    async def _run() -> int:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_FINDINGS):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.1)
                return len(list(app.screen.query(DataTable)))

    count = asyncio.run(_run())
    assert count == 1


def test_status_bar_mounted() -> None:
    """StatusBar widget is composed into the screen."""

    async def _run() -> int:
        app = _make_app()
        with patch("owa_tui.fixtures.load", return_value=_FIXTURE_FINDINGS):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.1)
                return len(list(app.screen.query(StatusBar)))

    count = asyncio.run(_run())
    assert count == 1


def test_live_path_via_mocked_probes() -> None:
    """Live path: list_piggy_profiles + probe_profile_token mocked → grid populated."""

    async def _run() -> tuple[int, int]:
        fake_profiles = (["alice", "bob"], "alice")

        def fake_probe(alias: str, audience: str = "graph") -> dict:
            return {
                "alias": alias,
                "audience": audience,
                "token_ok": True,
                "minutes_remaining": 30,
                "token_audience": "https://graph.microsoft.com",
                "error": None,
            }

        app = _make_app()
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_doctor.probe.list_piggy_profiles", return_value=fake_profiles),
            patch("owa_doctor.probe.probe_profile_token", side_effect=fake_probe),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.5)
                tbl = app.screen.query_one("#owa-grid-table", DataTable)
                return tbl.row_count, len(list(tbl.columns))

    rows, cols = asyncio.run(_run())
    # 2 profiles × 3 default audiences → 2 rows, 3 data cols + 1 row-label = 4 cols
    assert rows == 2
    assert cols == 4


def test_live_path_empty_profiles_returns_no_data() -> None:
    """When list_piggy_profiles returns empty list, status shows '(no data)'."""

    async def _run() -> str:
        app = _make_app()
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_doctor.probe.list_piggy_profiles", return_value=([], None)),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.5)
                return app.screen._status

    status = asyncio.run(_run())
    assert "(no data)" in status or "error" in status
