"""CalendarGrid: pure renderers plus the v toggle on the cal screen."""

from __future__ import annotations

import asyncio
from datetime import date

from rich.console import Console

from owa_tui.screens.cal.calendar import CalendarGrid, anchor_day, render_grid

EVENTS = [
    {"id": "a", "subject": "Standup", "start": "2026-09-28T09:00:00", "end": "2026-09-28T09:30:00"},
    {"id": "b", "subject": "Workshop", "start": "2026-09-28T13:00:00", "end": "2026-09-28T15:30:00"},
    {"id": "c", "subject": "Ferie", "start": "2026-09-30T00:00:00", "end": "2026-10-02T00:00:00", "isAllDay": True},
]
TODAY = date(2026, 9, 28)


def _text(renderable) -> str:
    console = Console(width=120, record=True, file=open("/dev/null", "w"))  # noqa: SIM115
    console.print(renderable)
    return console.export_text()


def test_day_timeline_places_events_on_their_hours() -> None:
    lines = _text(render_grid(EVENTS, "today", 0, TODAY)).splitlines()
    by_hour = {ln[:5]: ln for ln in lines}
    assert "09:00 Standup" in by_hour["09:00"]
    assert "13:00 Workshop" in by_hour["13:00"]
    assert "┆ Workshop" in by_hour["14:00"] and "┆ Workshop" in by_hour["15:00"]
    assert "Workshop" not in by_hour["16:00"]


def test_week_grid_has_seven_day_columns_and_spans_all_day_events() -> None:
    out = _text(render_grid(EVENTS, "week", None, TODAY))
    assert out.splitlines()[0].split()[:2] == ["Mon", "28.09"]
    assert "Sun 04.10" in out
    assert out.count("all-day Ferie") == 2  # Wed 30.09 and Thu 01.10, end is exclusive


def test_month_grid_caps_cells_but_always_shows_the_selected_event() -> None:
    many = [
        {"subject": f"m{n}", "start": f"2026-09-15T{8 + n:02d}:00:00", "end": f"2026-09-15T{9 + n:02d}:00:00"}
        for n in range(5)
    ]
    out = _text(render_grid(many, "month", 4, TODAY))
    assert "m0" in out and "m4" in out and "m3" not in out and "+2" in out


def test_anchor_falls_back_to_first_event_outside_the_period() -> None:
    june = [{"subject": "x", "start": "2026-06-18T09:00:00"}]
    assert anchor_day(june, "week", TODAY) == date(2026, 6, 18)
    assert anchor_day(EVENTS, "week", TODAY) == TODAY
    assert anchor_day([], "month", TODAY) == TODAY


def test_v_toggles_to_calendar_view_and_keeps_selection(monkeypatch) -> None:
    from textual.app import App

    import owa_tui.screens.cal.fetch as fetch_mod
    from owa_tui.screens.cal import CalScreen
    from owa_tui.screens.cal.settings import CalSettings

    async def _fake(fn, *a, **k):
        return {"value": [
            {"Id": "a", "Subject": "Standup", "Start": {"DateTime": "2026-09-28T09:00:00"},
             "End": {"DateTime": "2026-09-28T09:30:00"}},
            {"Id": "b", "Subject": "Workshop", "Start": {"DateTime": "2026-09-28T13:00:00"},
             "End": {"DateTime": "2026-09-28T15:30:00"}},
        ]}

    monkeypatch.setattr(fetch_mod.asyncio, "to_thread", _fake)
    saved: list[dict] = []

    class _App(App[None]):
        def on_mount(self) -> None:
            s = CalScreen(config={}, access_token="fake", api_base="https://fake.api")
            s._settings = CalSettings(day_range="week")
            s._persist_settings = lambda: saved.append(s._settings.to_config_patch())  # type: ignore[method-assign]
            self.push_screen(s)

    async def run():
        app = _App()
        async with app.run_test(size=(120, 30)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("j", "v")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.pause()
            scr = app.screen
            grid = scr._agenda()
            first = (type(grid).__name__, grid.index, app.focused is grid, grid.mode)
            await pilot.press("k")
            await pilot.pause()
            subject = scr._current_event()["subject"]
            await pilot.press("v")
            await app.workers.wait_for_complete()
            await pilot.pause()
            await pilot.pause()
            return first, subject, type(scr._agenda()).__name__, scr._agenda().index

    first, subject, back, idx = asyncio.run(run())
    assert first == ("CalendarGrid", 1, True, "week")
    assert subject == "Standup"
    assert (back, idx) == ("AgendaList", 0)
    assert saved[0]["tui_view"] == "calendar" and saved[-1]["tui_view"] == "list"
    assert isinstance(CalendarGrid(), CalendarGrid)
