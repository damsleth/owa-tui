"""Pure SWODP week-grid logic: cards -> grid -> write rows, calendar fill."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from owa_tui.screens.swodp import plan

FIXTURES = Path(__file__).resolve().parents[3] / "e2e" / "fixtures"
MONDAY = date(2026, 9, 14)
CATS = {"Admin": "admin"}


def _cards() -> list[dict]:
    return json.loads((FIXTURES / "swodp.json").read_text())


def _rows() -> list[dict]:
    return plan.cards_to_rows(_cards(), MONDAY, CATS)


def test_cards_to_grid_matches_week_38_reference() -> None:
    cols, grid = plan.grid_data(_rows())
    assert cols == ["man", "tir", "ons", "tor", "fre", "lør", "søn", "sum"]
    assert grid == [
        ("NOCOS T1PRJTSK4228809", ["7.5", "7", "2", "7.5", "7.5", "0", "0", "31.5"]),
        ("UNE T1PRJTSK4231733", ["0", "1", "4", "0", "0", "0", "0", "5"]),
        ("Admin", ["3", "0", "0", "0", "0", "0", "0", "3"]),
        ("per dag", ["10.5", "8", "6", "7.5", "7.5", "0", "0", "39.5"]),
    ]


def test_cards_outside_week_are_dropped_and_category_uses_raw_value() -> None:
    rows = _rows()
    assert len(rows) == 3  # the fixture's week-37 card is filtered out
    assert rows[2]["category"] == "admin" and rows[2]["key"] == "category:admin"
    assert plan.cards_to_rows(_cards(), MONDAY, {})[2]["category"] == "admin"  # lower() fallback


def test_clean_grid_writes_nothing() -> None:
    rows = _rows()
    assert plan.rows_to_write(rows) == []
    assert plan.diff_lines(rows) == []


def test_edit_remove_and_new_rows_build_contract_rows() -> None:
    rows = _rows()
    rows[0]["days"][1] = 6.0
    rows[1]["remove"] = True
    fresh = plan.new_row({"category": "sick"}, "Sick", "flu")
    fresh["days"][4] = 7.5
    rows.append(fresh)
    gone = plan.new_row({"category": "vacation"}, "Vacation")
    gone["remove"] = True
    rows.append(gone)

    written = plan.rows_to_write(rows)
    assert written == [
        {
            "taskNumber": "T1PRJTSK4228809",
            "days": [7.5, 6.0, 2.0, 7.5, 7.5, 0.0, 0.0],
            "description": rows[0]["description"],
        },
        {
            "taskNumber": "T1PRJTSK4231733",
            "days": [0.0, 1.0, 4.0, 0.0, 0.0, 0.0, 0.0],
            "description": rows[1]["description"],
            "remove": True,
        },
        {"category": "sick", "days": [0, 0, 0, 0, 7.5, 0, 0], "description": "flu"},
    ]
    assert plan.diff_lines(rows) == [
        "update  NOCOS T1PRJTSK4228809: tir 7→6",
        "remove  UNE T1PRJTSK4231733",
        "create  Sick: fre 7.5",
    ]
    # removed rows drop out of the sums
    assert plan.grid_data(rows)[1][-1] == (
        "per dag", ["10.5", "6", "2", "7.5", "15", "0", "0", "41"]
    )


def test_terminal_rows_never_write() -> None:
    rows = _rows()
    rows[0]["state"] = "Submitted"
    rows[0]["days"][0] = 1.0
    assert plan.rows_to_write(rows) == []


def test_round_half_is_half_up() -> None:
    assert [plan.round_half(h) for h in (0.2, 0.25, 0.74, 0.75, 2.25)] == [0, 0.5, 0.5, 1, 2.5]


def _ev(start: str, end: str, cats: list[str], **kw) -> dict:
    return {"start": start, "end": end, "categories": cats, "showAs": "busy", **kw}


def test_events_to_hours_maps_rounds_and_reports_unmapped() -> None:
    events = [
        _ev("2026-09-15T09:00:00", "2026-09-15T10:15:00", ["NC NOCOS"]),
        _ev("2026-09-15T13:00:00", "2026-09-15T14:00:00", ["NC NOCOS"]),
        _ev("2026-09-15T11:00:00", "2026-09-15T11:30:00", ["CC LUNCH"]),  # ignored
        _ev("2026-09-16T09:00:00", "2026-09-16T11:00:00", ["Mystery"]),  # unmapped
        _ev("2026-09-16T09:00:00", "2026-09-16T17:00:00", ["CC ADM"], isAllDay=True),
        _ev("2026-09-17T09:00:00", "2026-09-17T10:00:00", ["CC ADM"], showAs="free"),
        _ev("2026-09-17T09:00:00", "2026-09-17T10:00:00", []),  # no category
        _ev("2026-09-21T09:00:00", "2026-09-21T10:00:00", ["CC ADM"]),  # next week
        _ev("2026-09-18T08:00:00", "2026-09-18T11:00:00", ["CC ADM"]),
    ]
    hours, specs, unmapped = plan.events_to_hours(events, MONDAY, plan.DEFAULT_CATEGORY_MAP)
    assert hours == {
        "T1PRJTSK4228809": [0, 2.5, 0, 0, 0, 0, 0],  # 2.25h -> 2.5
        "category:admin": [0, 0, 0, 0, 3, 0, 0],
    }
    assert specs["category:admin"]["description"] == "Intern"
    assert unmapped == {"Mystery": 2.0}


def test_merge_fill_fills_empty_keeps_filled_skips_terminal_adds_new() -> None:
    rows = _rows()
    rows[1]["state"] = "Approved"  # UNE row is read-only
    hours = {
        "T1PRJTSK4228809": [0, 7, 0, 0, 0, 2, 0],  # tir matches, lør empty -> fill
        "T1PRJTSK4231733": [5, 0, 0, 0, 0, 0, 0],  # terminal -> untouched
        "category:admin": [4, 0, 0, 1, 0, 0, 0],  # man differs -> kept, tor filled
        "category:sick": [0, 0, 0, 0, 7.5, 0, 0],  # no row -> new
    }
    specs = {"category:sick": {"category": "sick", "description": "flu"}}
    filled, kept = plan.merge_fill(rows, hours, specs)
    assert (filled, kept) == (3, 1)
    assert rows[0]["days"][5] == 2 and rows[1]["days"][0] == 0
    assert rows[2]["days"][:4] == [3, 0, 0, 1]
    assert rows[3]["label"] == "Sick" and rows[3]["state"] == plan.NEW
    assert rows[3]["description"] == "flu"


def test_week_title_and_labels() -> None:
    assert plan.week_title(MONDAY, "prod") == "Uke 38 · 14.09–20.09.2026 · prod"
    assert plan.monday_of(date(2026, 9, 20)) == MONDAY
    assert plan.row_label({"taskNumber": "T1X12345"}) == "T1X12345"
    assert plan.row_label({"taskNumber": "T1X12345"}, "UNE: stuff") == "UNE T1X12345"
