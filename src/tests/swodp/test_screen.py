"""SwodpScreen pilot tests, fixture mode only (no Edge, no ServiceNow)."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import DataTable, Input, Label

import owa_tui
from owa_tui.screens.base.screen import _SearchModal
from owa_tui.screens.swodp import adapter
from owa_tui.screens.swodp.screen import SwodpScreen

FIXTURES = Path(__file__).resolve().parents[3] / "e2e" / "fixtures"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OWA_TUI_FIXTURES", str(FIXTURES))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


def _row(tbl: DataTable, r: int) -> list[str]:
    return [str(c) for c in tbl.get_row_at(r)]


async def _answer(pilot, value: str) -> None:
    await pilot.pause()
    assert isinstance(pilot.app.screen, _SearchModal)
    pilot.app.screen.query_one(Input).value = value
    await pilot.press("enter")
    await pilot.pause()


def _run(steps, **screen_kw):
    """Push SwodpScreen, run ``steps(pilot, screen, table)``, return its result."""

    async def main():
        app = owa_tui.OwaTuiApp()
        async with app.run_test(size=(140, 40)) as pilot:
            app.push_screen(SwodpScreen(**screen_kw))
            await pilot.pause(0.4)
            sc = app.screen
            return await steps(pilot, sc, sc.query_one(DataTable))

    return asyncio.run(main())


def test_opens_on_fixture_week_with_sums_and_title() -> None:
    async def steps(pilot, sc, tbl):
        title = str(sc.query_one("#owa-grid-breadcrumb", Label).content)
        return title, sc._status, _row(tbl, 3), tbl.cursor_coordinate.column

    title, status, per_dag, col = _run(steps)
    assert title == "Uke 38 · 14.09–20.09.2026 · prod"
    assert status == "3 kort · 39.5 timer"
    assert per_dag[0] == "per dag" and per_dag[-1] == "[bold]39.5[/bold]"
    assert col == 1  # cursor starts on Monday, not the label column


def test_edit_cell_validates_and_marks_dirty() -> None:
    async def steps(pilot, sc, tbl):
        out = []
        await pilot.press("j", "l", "enter")  # UNE, tirsdag
        await _answer(pilot, "abc")
        out.append(sc._status)
        await pilot.press("i")
        await _answer(pilot, "0.3")
        out.append(sc._status)
        await pilot.press("i")
        await _answer(pilot, "6,5")
        out.append((sc._status, _row(tbl, 1)[2], _row(tbl, 1)[-1]))
        await pilot.press("x")
        await pilot.pause()
        out.append(_row(tbl, 1)[2])
        return out

    bad, step, edited, zeroed = _run(steps)
    assert bad == "not a number: 'abc'"
    assert step == "hours must be 0–24 in steps of 0.25"
    assert edited == (
        "3 kort · 45 timer · 1 unwritten (w to write)",
        "[bold yellow]6.5[/bold yellow]",
        "[bold]10.5[/bold]",
    )
    assert zeroed == "[bold yellow]0[/bold yellow]"


def test_terminal_week_is_read_only() -> None:
    async def steps(pilot, sc, tbl):
        await pilot.press("x")
        await pilot.pause()
        zero = sc._status
        await pilot.press("D")
        await pilot.pause()
        return zero, sc._status, _row(tbl, 0)[1], type(pilot.app.screen).__name__

    zero, remove, cell, screen = _run(steps, week_start=date(2026, 9, 7))
    assert zero == remove == "NOCOS T1PRJTSK4228809 is Approved — read-only"
    assert cell == "[dim]7.5[/dim]"
    assert screen == "SwodpScreen"


def test_non_editable_cells_explain_why() -> None:
    async def steps(pilot, sc, tbl):
        out = []
        tbl.move_cursor(row=3, column=1)  # per dag
        await pilot.press("i")
        out.append(sc._status)
        tbl.move_cursor(row=0, column=8)  # sum column
        await pilot.press("i")
        out.append(sc._status)
        return out

    assert _run(steps) == ["not an editable row", "move to a day column (man–søn) to edit"]


def test_remove_add_description_and_write_guard() -> None:
    async def steps(pilot, sc, tbl):
        out = []
        await pilot.press("w")
        out.append(sc._status)  # clean grid
        await pilot.press("D")  # NOCOS -> remove
        await pilot.pause()
        out.append((sc._status.split(" · ")[0], _row(tbl, 0)[1]))
        await pilot.press("i")
        out.append(sc._status)
        await pilot.press("D")  # undo
        await pilot.press("a")
        await _answer(pilot, "admin")
        out.append(sc._status)
        await pilot.press("a")
        await _answer(pilot, "nonsense!")
        out.append(sc._status)
        await pilot.press("a")
        await _answer(pilot, "t1prjtsk9999999")
        out.append(sc._status.split(" · ")[0])
        tbl.move_cursor(row=3, column=3)
        await pilot.press("i")
        await _answer(pilot, "2")
        await pilot.press("w")
        await pilot.pause()
        out.append(sc._status)  # new row lacks description
        await pilot.press("e")
        await _answer(pilot, "Nytt prosjekt: oppstart")
        await pilot.press("w")
        await pilot.pause()
        prompt = str(pilot.app.screen.query(Label).first().content)
        await _answer(pilot, "n")
        out.append((prompt, sc._status))
        await pilot.press("D")  # dropping a new row removes it outright
        await pilot.pause()
        out.append((sc._status.split(" · ")[0], tbl.row_count))
        return out

    (clean, removed, blocked, dup, unknown, added, no_desc, (prompt, cancelled), dropped) = _run(
        steps
    )
    assert clean == "nothing to write"
    assert removed == ("NOCOS T1PRJTSK4228809: remove on write", "[strike dim]7.5[/strike dim]")
    assert blocked == "NOCOS T1PRJTSK4228809 is marked for removal (D to undo)"
    assert dup == "admin is already in this week"
    assert unknown.startswith("unknown row 'nonsense!'")
    assert added == "added T1PRJTSK9999999 — press e to set a description"
    assert no_desc == "cannot write T1PRJTSK9999999: row 1 requires a non-empty description"
    assert prompt.splitlines() == [
        "Write to SWODP, Uke 38 · 14.09–20.09.2026 · prod:",
        "create  Nytt T1PRJTSK9999999: ons 2",
        "",
        "Type y and Enter to write (cards stay Pending; nothing is submitted).",
    ]
    assert cancelled == "write cancelled"
    assert dropped == ("dropped new row Nytt T1PRJTSK9999999", 4)


def test_new_row_reuses_description_from_the_range() -> None:
    async def steps(pilot, sc, tbl):
        sc._plan.pop(0)  # drop NOCOS locally to re-add it from the range
        sc._render_plan()
        await pilot.press("a")
        await _answer(pilot, "T1PRJTSK4228809")
        return sc._plan[-1]["description"], sc._status.split(" · ")[0]

    desc, status = _run(steps)
    assert desc.startswith("NOCOS forvaltning: prodsetting")
    assert status == "added NOCOS T1PRJTSK4228809"


def test_write_dry_run_then_reload() -> None:
    async def steps(pilot, sc, tbl):
        await pilot.press("l")
        await pilot.press("i")
        await _answer(pilot, "6")
        await pilot.press("w")
        await _answer(pilot, "y")
        await pilot.pause(0.5)
        return sc._status, _row(tbl, 0)[2]

    status, cell = _run(steps)
    assert status == "1 updated (fixture dry-run) · 3 kort · 39.5 timer"
    assert cell == "7"  # reloaded from the (unchanged) fixture


def test_write_reports_failure_and_details() -> None:
    async def steps(pilot, sc, tbl):
        out = []
        await pilot.press("x")
        with patch.object(adapter, "write", side_effect=adapter.SwodpAuthError("expired — Run: x")):
            await pilot.press("w")
            await _answer(pilot, "yes")
            await pilot.pause(0.3)
        out.append((sc._status, sc._session))
        results = [{"taskNumber": "T1PRJTSK4228809", "action": "updated", "detail": "comments empty"}]
        with patch.object(adapter, "write", return_value=results):
            await pilot.press("x")
            await pilot.press("w")
            await _answer(pilot, "y")
            await pilot.pause(0.5)
        out.append(sc._status.split(" · ")[0])
        return out

    failed, detail = _run(steps)
    assert failed == ("write failed: expired — Run: x", None)
    assert detail == "1 updated — T1PRJTSK4228809: comments empty (fixture dry-run)"


def test_fill_from_calendar_reports_kept_and_unmapped() -> None:
    async def steps(pilot, sc, tbl):
        await pilot.press("c")
        await pilot.pause(0.5)
        return sc._status, _row(tbl, 2)[4]

    status, admin_thu = _run(steps)
    assert status == (
        "calendar: 1 cell(s) filled, 3 kept (already filled; edit by hand), "
        "unmapped: XX KUNDE 2h (add to swodp.category_map in tui.json) · "
        "3 kort · 41.5 timer · 1 unwritten (w to write)"
    )
    assert admin_thu == "[bold yellow]2[/bold yellow]"


def test_fill_from_calendar_error_goes_to_status() -> None:
    async def steps(pilot, sc, tbl):
        with patch.object(adapter, "calendar_events", side_effect=RuntimeError("no token")):
            await pilot.press("c")
            await pilot.pause(0.3)
        return sc._status

    assert _run(steps) == "calendar: no token"


def test_week_navigation_discards_edits() -> None:
    async def steps(pilot, sc, tbl):
        out = []
        await pilot.press("x")
        await pilot.press("left_square_bracket")
        await pilot.pause(0.4)
        out.append((sc._monday, sc._status))
        await pilot.press("right_square_bracket")
        await pilot.pause(0.4)
        out.append(sc._monday)
        await pilot.press("t")
        await pilot.pause(0.4)
        out.append((sc._monday.weekday(), sc._status))
        return out

    prev, back, (weekday, empty) = _run(steps)
    assert prev == (date(2026, 9, 7), "discarded 1 unwritten row(s) · 1 kort · 37.5 timer")
    assert back == date(2026, 9, 14)
    assert weekday == 0 and empty == "0 kort · 0 timer"


def test_auth_error_resets_session_and_shows_hint() -> None:
    err = adapter.SwodpAuthError("not authenticated — Run: owa-swodp setup --instance prod")

    async def steps(pilot, sc, tbl):
        with patch.object(adapter, "week", side_effect=err):
            await pilot.press("r")
            await pilot.pause(0.4)
        return sc._status, sc._session

    status, session = _run(steps)
    assert status == "error: not authenticated — Run: owa-swodp setup --instance prod"
    assert session is None


def test_help_and_detail() -> None:
    async def steps(pilot, sc, tbl):
        sc.handle_menu_result("help")
        helptext = sc._status
        tbl.move_cursor(row=0, column=0)
        await pilot.press("enter")
        await pilot.pause()
        return helptext, sc._status, sc.menu_config()[0]

    helptext, detail, menu = _run(steps)
    assert "w write" in helptext and "submit" not in helptext
    assert detail.startswith("NOCOS T1PRJTSK4228809 · Pending · NOCOS forvaltning")
    assert menu == "Timesheet (SWODP) — prod · calendar swon"


def test_config_is_read_and_seeded(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "owa-tui" / "tui.json"
    sc = SwodpScreen()
    monkeypatch.setattr("owa_tui.fixtures.enabled", lambda: False)

    class _App:
        is_headless = False

    with patch.object(SwodpScreen, "app", _App()):
        sc._seed_config()
    saved = json.loads(cfg.read_text())["swodp"]
    assert saved["instance"] == "prod" and saved["cal_profile"] == "swon"
    assert saved["category_map"]["CC LUNCH"] is None

    saved.update(instance="uat", cal_profile="nc")
    cfg.write_text(json.dumps({"swodp": saved}))
    again = SwodpScreen(week_start=date(2026, 9, 16))
    assert (again._instance, again._settings["cal_profile"], again._monday) == (
        "uat", "nc", date(2026, 9, 14)
    )


def test_rapid_week_changes_render_the_last_week() -> None:
    async def steps(pilot, sc, tbl):
        await pilot.press("left_square_bracket", "right_square_bracket", "left_square_bracket")
        await pilot.pause(0.6)
        title = str(sc.query_one("#owa-grid-breadcrumb", Label).content)
        return title, [r["label"] for r in sc._plan], _row(tbl, 0)[1]

    title, labels, cell = _run(steps)
    assert title.startswith("Uke 37")
    assert labels == ["NOCOS T1PRJTSK4228809"]
    assert cell == "[dim]7.5[/dim]"  # Approved week: styling matches the rows shown
