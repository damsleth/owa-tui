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


def _text(renderable, width: int = 120) -> str:
    console = Console(width=width, record=True, file=open("/dev/null", "w"))  # noqa: SIM115
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


def test_month_grid_shows_every_event_of_a_day() -> None:
    many = [
        {"subject": f"m{n}", "start": f"2026-09-15T{8 + n:02d}:00:00", "end": f"2026-09-15T{9 + n:02d}:00:00"}
        for n in range(6)
    ]
    out = _text(render_grid(many, "month", 4, TODAY))
    assert all(f"m{n}" in out for n in range(6)) and "+" not in out.replace("+47", "")

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


def _grid_app(events, mode):
    from textual.app import App, ComposeResult

    class _App(App[None]):
        def compose(self) -> ComposeResult:
            grid = CalendarGrid(id="g", mode=mode)
            grid._today = TODAY
            yield grid

        def on_mount(self) -> None:
            self.query_one(CalendarGrid).update_rows(events)
            self.query_one(CalendarGrid).focus()

    return _App()


def _walk(events, mode, keys):
    async def run():
        app = _grid_app(events, mode)
        out = []
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            g = app.query_one(CalendarGrid)
            out.append((g._day, (g.current_item() or {}).get("id")))
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
                out.append((g._day, (g.current_item() or {}).get("id")))
        return out

    return asyncio.run(run())


WEEK = [
    {"id": "mon9", "subject": "a", "start": "2026-09-28T09:00:00", "end": "2026-09-28T10:00:00"},
    {"id": "mon14", "subject": "b", "start": "2026-09-28T14:00:00", "end": "2026-09-28T15:00:00"},
    {"id": "tue10", "subject": "c", "start": "2026-09-29T10:00:00", "end": "2026-09-29T11:00:00"},
    {"id": "tue15", "subject": "d", "start": "2026-09-29T15:00:00", "end": "2026-09-29T16:00:00"},
]


def test_week_grid_hl_move_days_and_jk_move_within_the_day() -> None:
    d = date
    steps = _walk(WEEK, "week", ["j", "l", "k", "l", "right", "h", "left", "left", "h"])
    assert steps == [
        (d(2026, 9, 28), "mon9"),
        (d(2026, 9, 28), "mon14"),  # j: next event that day
        (d(2026, 9, 29), "tue15"),  # l: next day, nearest start to 14:00
        (d(2026, 9, 29), "tue10"),  # k
        (d(2026, 9, 30), None),  # l: an empty day is selectable
        (d(2026, 10, 1), None),  # →
        (d(2026, 9, 30), None),  # h
        (d(2026, 9, 29), "tue10"),  # ←: first event of the day
        (d(2026, 9, 28), "mon9"),
        (d(2026, 9, 28), "mon9"),  # h at Monday: stays in the fetched week
    ]


def test_month_grid_jk_step_events_first_then_move_a_week() -> None:
    d = date
    steps = _walk(WEEK, "month", ["j", "j", "k", "k", "k", "l", "j", "k"])
    assert steps == [
        (d(2026, 9, 28), "mon9"),
        (d(2026, 9, 28), "mon14"),  # j: the event below in the same day
        (d(2026, 9, 28), "mon14"),  # j past the last event: 5 Oct is outside September
        (d(2026, 9, 28), "mon9"),  # k: the event above
        (d(2026, 9, 21), None),  # k past the first event: a week up (an empty day)
        (d(2026, 9, 14), None),
        (d(2026, 9, 15), None),  # l
        (d(2026, 9, 22), None),  # j on an empty day: a week down
        (d(2026, 9, 15), None),
    ]


def test_month_grid_moving_up_into_a_day_lands_on_its_last_event() -> None:
    events = [*WEEK, {"id": "sep21a", "subject": "x", "start": "2026-09-21T09:00:00", "end": "2026-09-21T10:00:00"},
              {"id": "sep21b", "subject": "y", "start": "2026-09-21T13:00:00", "end": "2026-09-21T14:00:00"}]
    steps = _walk(events, "month", ["k", "k", "j", "j"])
    assert [s[1] for s in steps] == ["mon9", "sep21b", "sep21a", "sep21b", "mon9"]


def test_month_grid_titles_get_the_squeeze_not_the_time() -> None:
    long = [  # every day of the week competes for width
        {"subject": "UNE Storgata med Qlik-konsulenten og mer", "start": f"2026-09-{d:02d}T10:00:00",
         "end": f"2026-09-{d:02d}T11:00:00"}
        for d in range(14, 21)
    ]
    out = _text(render_grid(long, "month", 0, TODAY), width=90)
    assert "10:00 UNE" in out and "…" in out

def test_cursor_day_is_marked_in_week_and_month_grids() -> None:
    out = _text(render_grid(WEEK, "week", None, TODAY, cursor=date(2026, 9, 30)))
    assert "Wed 30.09" in out
    month = _text(render_grid(WEEK, "month", None, TODAY, cursor=date(2026, 9, 15)))
    assert " 15 " in month


def test_calendar_view_moves_a_right_hand_reading_pane_underneath() -> None:
    from owa_tui.screens.cal import CalScreen
    from owa_tui.screens.cal.settings import CalSettings

    sc = CalScreen(config={})
    for view, pane, used in [
        ("calendar", "right", "bottom"),
        ("calendar", "bottom", "bottom"),
        ("calendar", "off", "off"),
        ("list", "right", "right"),
    ]:
        sc._settings = CalSettings(view=view, reading_pane=pane)
        assert sc._reading_pane() == used, (view, pane)
