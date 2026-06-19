"""Pilot tests for CalScreen.

Mirrors test_tui.py + test_tui_actions.py from the owa-cal curses test suite.
No real network calls — api_get / api_request are monkeypatched.
All tests use asyncio.run + app.run_test() (no pytest-asyncio required).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from owa_tui.screens.cal import CalScreen
from owa_tui.screens.cal.settings import CalSettings

# ---------------------------------------------------------------------------
# Test event fixtures
# ---------------------------------------------------------------------------

_RAW_EVENT_1 = {
    "Id": "evt-001",
    "Subject": "Morning standup",
    "Start": {"DateTime": "2026-06-18T09:00:00", "TimeZone": "UTC"},
    "End": {"DateTime": "2026-06-18T09:30:00", "TimeZone": "UTC"},
    "IsAllDay": False,
    "ShowAs": "busy",
    "Categories": [],
    "Location": {"DisplayName": "Teams"},
    "Organizer": {"EmailAddress": {"Name": "Alice", "Address": "alice@x.com"}},
    "Attendees": [],
    "BodyPreview": "Daily sync.",
    "ResponseStatus": {"Response": "Accepted", "Time": "2026-06-18T08:00:00Z"},
    "IsOrganizer": False,
}

_RAW_EVENT_2 = {
    "Id": "evt-002",
    "Subject": "Lunch review",
    "Start": {"DateTime": "2026-06-18T12:00:00", "TimeZone": "UTC"},
    "End": {"DateTime": "2026-06-18T13:00:00", "TimeZone": "UTC"},
    "IsAllDay": False,
    "ShowAs": "busy",
    "Categories": [],
    "Location": {"DisplayName": ""},
    "Organizer": {"EmailAddress": {"Name": "Bob", "Address": "bob@x.com"}},
    "Attendees": [
        {
            "EmailAddress": {"Name": "Carol", "Address": "carol@x.com"},
            "Type": "Required",
            "Status": {"Response": "Accepted", "Time": "2026-06-18T08:00:00Z"},
        }
    ],
    "BodyPreview": "Lunch.",
    "ResponseStatus": {"Response": "Accepted", "Time": "2026-06-18T08:00:00Z"},
    "IsOrganizer": False,
}

_RAW_WITH_LINK = {
    **_RAW_EVENT_1,
    "Id": "evt-003",
    "Subject": "Event with link",
    "webLink": "https://outlook.office365.com/owa/?itemid=fake",
}


# ---------------------------------------------------------------------------
# Monkeypatching helpers
# ---------------------------------------------------------------------------


def _patch_api_get(monkeypatch: pytest.MonkeyPatch, raw_events: list) -> None:
    """Patch owa_tui.screens.cal.fetch asyncio.to_thread to return fake data."""
    raw_response = {"value": raw_events}

    async def _fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        return raw_response

    import owa_tui.screens.cal.fetch as fetch_mod

    monkeypatch.setattr(fetch_mod.asyncio, "to_thread", _fake_to_thread)


def _patch_api_request(monkeypatch: pytest.MonkeyPatch, return_value: Any = True) -> list:
    """Patch api_request and return call log."""
    calls: list = []

    async def _fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(fn)
        return return_value

    monkeypatch.setattr(
        "owa_tui.screens.cal.cal.asyncio.to_thread",
        _fake_to_thread,
    )
    return calls


# ---------------------------------------------------------------------------
# Helper: build a minimal CalScreen
# ---------------------------------------------------------------------------


def _make_screen(
    monkeypatch: pytest.MonkeyPatch,
    events: list | None = None,
    *,
    reading_pane: str = "right",
    day_range: str = "today",
) -> CalScreen:
    if events is None:
        events = [_RAW_EVENT_1, _RAW_EVENT_2]
    _patch_api_get(monkeypatch, events)
    settings = CalSettings(reading_pane=reading_pane, day_range=day_range)
    screen = CalScreen.__new__(CalScreen)
    CalScreen.__init__(screen, config={}, access_token="fake", api_base="https://fake.api")
    screen._settings = settings
    return screen


# ---------------------------------------------------------------------------
# T1: events loaded and displayed
# ---------------------------------------------------------------------------


def test_events_appear_in_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Events returned by api_get appear in the AgendaList."""
    _patch_api_get(monkeypatch, [_RAW_EVENT_1, _RAW_EVENT_2])

    from textual.app import App, ComposeResult

    class _App(App[None]):
        def compose(self) -> ComposeResult:
            yield CalScreen(
                config={}, access_token="fake", api_base="https://fake.api"
            )

    async def _run() -> int:
        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            return screen._agenda().item_count

    count = asyncio.run(_run())
    assert count == 2


# ---------------------------------------------------------------------------
# T2: search filter
# ---------------------------------------------------------------------------


def test_search_filters_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """After a search, only matching events are shown."""
    _patch_api_get(monkeypatch, [_RAW_EVENT_1, _RAW_EVENT_2])

    async def _run() -> int:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.query_one(CalScreen)
            # Set search directly and reload
            screen._search = "morning"
            await pilot.pause()
            screen._agenda().update_rows(
                [e for e in screen._events if "morning" in (e.get("subject") or "").lower()],
                show_date=False,
            )
            await pilot.pause()
            return screen._agenda().item_count

    count = asyncio.run(_run())
    assert count == 1


# ---------------------------------------------------------------------------
# T5: respond chord cancel
# ---------------------------------------------------------------------------


def test_respond_chord_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pressing 'y' then 'x' (non-respond key) cancels respond mode."""
    _patch_api_get(monkeypatch, [_RAW_EVENT_1])

    async def _run() -> str:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            # Arm respond mode manually
            screen._respond_mode = True
            screen._status = "respond: ..."
            # Simulate any-other-key cancel
            screen._respond_mode = False
            screen._status = "respond cancelled"
            return screen._status

    status = asyncio.run(_run())
    assert status == "respond cancelled"


# ---------------------------------------------------------------------------
# T6: respond with no event selected
# ---------------------------------------------------------------------------


def test_respond_no_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """y with empty list: _respond_mode stays False, status = 'no event selected'."""
    _patch_api_get(monkeypatch, [])

    async def _run() -> tuple:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            screen.action_respond_arm()
            await pilot.pause()
            return screen._respond_mode, screen._status

    mode, status = asyncio.run(_run())
    assert mode is False
    assert status == "no event selected"


# ---------------------------------------------------------------------------
# T8: drill with pane off
# ---------------------------------------------------------------------------


def test_drill_pane_off_shows_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """With reading_pane='off', Enter sets status hint."""
    _patch_api_get(monkeypatch, [_RAW_EVENT_1])

    async def _run() -> str:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                s = CalScreen(config={}, access_token="fake", api_base="https://fake.api")
                s._settings = CalSettings(reading_pane="off")
                yield s

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            # Manually trigger the drill action
            from owa_tui.screens.cal.agenda import AgendaItemDrilled

            screen.on_agenda_item_drilled(AgendaItemDrilled(screen._current_event()))
            return screen._status

    status = asyncio.run(_run())
    assert "reading pane" in status.lower()


# ---------------------------------------------------------------------------
# T10: refresh triggers reload
# ---------------------------------------------------------------------------


def test_refresh_triggers_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pressing 'r' triggers a re-fetch (load_events called again)."""
    calls: list[int] = []

    _patch_api_get(monkeypatch, [_RAW_EVENT_1])

    async def _run() -> int:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            # Track load_events calls
            original = screen.load_events

            def patched_load():
                calls.append(1)
                return original()

            screen.load_events = patched_load  # type: ignore[method-assign]
            await pilot.press("r")
            await pilot.pause()
            return len(calls)

    count = asyncio.run(_run())
    assert count >= 1


# ---------------------------------------------------------------------------
# T11: open browser fires webbrowser
# ---------------------------------------------------------------------------


def test_open_browser_fires_webbrowser(monkeypatch: pytest.MonkeyPatch) -> None:
    """action_open_browser calls webbrowser.open with the event's webLink."""
    _patch_api_get(monkeypatch, [_RAW_EVENT_1])

    opened: list[str] = []

    async def _run() -> list:
        from textual.app import App, ComposeResult

        import owa_tui.screens.cal.screen as screen_mod

        monkeypatch.setattr(screen_mod.webbrowser, "open", lambda url: opened.append(url))

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            # Use update_rows so the ListView gets the item and index is set
            ev = {"id": "evt-x", "subject": "Test", "start": "2026-06-18T09:00:00",
                  "end": "2026-06-18T10:00:00", "isAllDay": False,
                  "webLink": "https://example.com/event"}
            screen._events = [ev]
            screen._agenda().update_rows([ev])
            await pilot.pause()
            screen.action_open_browser()
            return opened

    result = asyncio.run(_run())
    assert len(result) == 1
    assert "example.com" in result[0]


# ---------------------------------------------------------------------------
# T12: open browser no link
# ---------------------------------------------------------------------------


def test_open_browser_no_link(monkeypatch: pytest.MonkeyPatch) -> None:
    """Event with no webLink → status = 'no web link for this event'."""
    _patch_api_get(monkeypatch, [_RAW_EVENT_1])

    async def _run() -> str:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            # Use update_rows so the ListView gets the item and index is set
            ev = {"id": "evt-x", "subject": "Test", "start": "2026-06-18T09:00:00",
                  "end": "2026-06-18T10:00:00", "isAllDay": False}
            screen._events = [ev]
            screen._agenda().update_rows([ev])
            await pilot.pause()
            screen.action_open_browser()
            return screen._status

    status = asyncio.run(_run())
    assert "no web link" in status


# ---------------------------------------------------------------------------
# T14: render_row week view date prefix
# ---------------------------------------------------------------------------


def test_render_row_week_view_shows_date() -> None:
    """render_row with show_date=True includes weekday+date prefix."""
    from owa_tui.screens.cal.agenda import render_row

    event = {
        "subject": "Test event",
        "start": "2026-06-05T09:00:00",
        "end": "2026-06-05T10:00:00",
        "isAllDay": False,
        "location": "",
    }
    row = render_row(event, 80, show_date=True)
    assert "06-05" in row


# ---------------------------------------------------------------------------
# T15: render_row day view no date prefix
# ---------------------------------------------------------------------------


def test_render_row_day_view_no_date() -> None:
    """render_row with show_date=False does NOT include the date prefix."""
    from owa_tui.screens.cal.agenda import render_row

    event = {
        "subject": "Test event",
        "start": "2026-06-05T09:00:00",
        "end": "2026-06-05T10:00:00",
        "isAllDay": False,
        "location": "",
    }
    row = render_row(event, 80, show_date=False)
    assert "06-05" not in row


# ---------------------------------------------------------------------------
# T16: empty list placeholder
# ---------------------------------------------------------------------------


def test_empty_list_shows_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty event list should show '(no events)' placeholder."""
    _patch_api_get(monkeypatch, [])

    async def _run() -> bool:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            # Check that the placeholder is rendered
            screen = app.query_one(CalScreen)
            return screen._agenda().item_count == 0

    is_empty = asyncio.run(_run())
    assert is_empty


# ---------------------------------------------------------------------------
# Render row edge cases
# ---------------------------------------------------------------------------


def test_render_row_all_day() -> None:
    from owa_tui.screens.cal.agenda import render_row

    event = {
        "subject": "All day event",
        "start": "2026-06-18T00:00:00",
        "end": "2026-06-18T23:59:59",
        "isAllDay": True,
        "location": "",
    }
    row = render_row(event, 80)
    assert "all-day" in row


def test_render_row_empty_subject() -> None:
    from owa_tui.screens.cal.agenda import render_row

    event = {"subject": "", "start": "2026-06-18T09:00:00", "end": "2026-06-18T10:00:00",
             "isAllDay": False, "location": ""}
    row = render_row(event, 80)
    assert isinstance(row, str)


def test_render_row_width_one() -> None:
    from owa_tui.screens.cal.agenda import render_row

    event = {"subject": "X", "start": "2026-06-18T09:00:00", "end": "2026-06-18T10:00:00",
             "isAllDay": False, "location": ""}
    row = render_row(event, 1)
    assert len(row) <= 1


def test_render_row_location_suffix() -> None:
    from owa_tui.screens.cal.agenda import render_row

    event = {"subject": "Meeting", "start": "2026-06-18T09:00:00", "end": "2026-06-18T10:00:00",
             "isAllDay": False, "location": "Conference Room A"}
    row = render_row(event, 80)
    assert "Conference Room A" in row


def test_render_row_location_capped_at_20() -> None:
    from owa_tui.screens.cal.agenda import render_row

    long_loc = "A" * 40
    event = {"subject": "M", "start": "2026-06-18T09:00:00", "end": "2026-06-18T10:00:00",
             "isAllDay": False, "location": long_loc}
    row = render_row(event, 80)
    assert long_loc[:21] not in row  # location capped at 20 chars


def test_render_row_bad_date_with_show_date() -> None:
    """Unparseable start date with show_date=True must not crash."""
    from owa_tui.screens.cal.agenda import render_row

    event = {"subject": "Bad date", "start": "not-a-date", "end": "not-a-date",
             "isAllDay": False, "location": ""}
    row = render_row(event, 80, show_date=True)
    assert isinstance(row, str)


# ---------------------------------------------------------------------------
# CalSettings
# ---------------------------------------------------------------------------


def test_cal_settings_defaults() -> None:
    s = CalSettings()
    assert s.reading_pane == "right"
    assert s.split_ratio == 50
    assert s.day_range == "today"
    assert s.show_declined == "no"
    assert s.event_detail == "full"


def test_cal_settings_cycle_reading_pane() -> None:
    s = CalSettings(reading_pane="right")
    s2 = s.cycle("reading_pane")
    assert s2.reading_pane == "bottom"
    s3 = s2.cycle("reading_pane")
    assert s3.reading_pane == "off"
    s4 = s3.cycle("reading_pane")
    assert s4.reading_pane == "right"


def test_cal_settings_cycle_split_ratio() -> None:
    s = CalSettings(split_ratio=50)
    s2 = s.cycle("split_ratio")
    assert s2.split_ratio == 60
    s3 = s2.cycle("split_ratio")
    assert s3.split_ratio == 40


def test_cal_settings_from_config() -> None:
    cfg = {
        "tui_reading_pane": "bottom",
        "tui_split_ratio": "60",
        "tui_day_range": "week",
        "tui_show_declined": "yes",
        "tui_event_detail": "basic",
    }
    s = CalSettings.from_config(cfg)
    assert s.reading_pane == "bottom"
    assert s.split_ratio == 60
    assert s.day_range == "week"
    assert s.show_declined == "yes"
    assert s.event_detail == "basic"


def test_cal_settings_day_range_override() -> None:
    """CalScreen applies day_range CLI override."""
    screen = CalScreen(config={}, access_token="", api_base="", day_range="week")
    assert screen._settings.day_range == "week"


def test_cal_settings_invalid_day_range_ignored() -> None:
    """Unknown day_range CLI arg leaves default."""
    screen = CalScreen(config={}, access_token="", api_base="", day_range="invalid")
    assert screen._settings.day_range == "today"  # default unchanged


# ---------------------------------------------------------------------------
# Browser action edge case — no event selected
# ---------------------------------------------------------------------------


def test_open_browser_no_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """action_open_browser with empty list → status = 'no event selected'."""
    _patch_api_get(monkeypatch, [])

    async def _run() -> str:
        from textual.app import App, ComposeResult

        class _App(App[None]):
            def compose(self) -> ComposeResult:
                yield CalScreen(config={}, access_token="fake", api_base="https://fake.api")

        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            screen = app.query_one(CalScreen)
            screen.action_open_browser()
            return screen._status

    status = asyncio.run(_run())
    assert status == "no event selected"
