"""plan.py — pure SWODP week-grid logic: cards -> rows -> write plan.

No Textual, no owa_swodp imports. A *row* is a plain dict::

    {"key": "T1PRJTSK4228809" | "category:admin",
     "label": "NOCOS T1PRJTSK4228809" | "Admin",
     "taskNumber": ... | "category": ...,     # exactly one, write-contract shape
     "days": [7 floats], "orig": [7 floats],  # orig = what the server has
     "description": str, "orig_description": str,
     "state": "Pending" | "Submitted" | ... | "New",
     "remove": bool}

A cell is dirty when ``days[i] != orig[i]``; a row is dirty when any cell is,
when it is flagged ``remove``, or when it is new.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

DAY_FIELDS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_LABELS = ("man", "tir", "ons", "tor", "fre", "lør", "søn")
TERMINAL_STATES = frozenset({"Submitted", "Approved", "Processed"})
NEW = "New"
SUM_LABEL = "per dag"

# Seeded into tui.json on first run; the user extends it there.
DEFAULT_CATEGORY_MAP: dict[str, dict[str, str] | None] = {
    "NC NOCOS": {"taskNumber": "T1PRJTSK4228809", "description": "NOCOS forvaltning"},
    "UNE 4LYF": {"taskNumber": "T1PRJTSK4231733", "description": "UNE"},
    "CC ADM": {"category": "admin", "description": "Intern"},
    "CC LUNCH": None,
}


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_title(monday: date, instance: str) -> str:
    sunday = monday + timedelta(days=6)
    week = monday.isocalendar()[1]
    return f"Uke {week} · {monday:%d.%m}–{sunday:%d.%m.%Y} · {instance}"


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def fmt(value: float) -> str:
    return f"{value:g}"


def identity_key(spec: dict) -> str:
    return spec.get("taskNumber") or f"category:{spec['category']}"


def is_editable(row: dict) -> bool:
    return row["state"] not in TERMINAL_STATES


def is_dirty(row: dict) -> bool:
    return (
        row["remove"]
        or row["state"] == NEW
        or row["days"] != row["orig"]
        or row["description"] != row["orig_description"]
    )


def row_label(spec: dict, description: str = "") -> str:
    """``NOCOS T1PRJTSK4228809`` for a task, ``Admin`` for a category.

    ponytail: the "Kort" prefix is the first word of the description (NOCOS,
    UNE); cards carry no project short name.
    """
    task = spec.get("taskNumber")
    if not task:
        return spec["category"].capitalize()
    words = description.split(":")[0].split()
    return f"{words[0]} {task}" if words else task


def cards_to_rows(cards: list[dict], monday: date, categories: dict[str, str]) -> list[dict]:
    """Cards for the week starting *monday* as grid rows.

    ``categories`` maps display name -> raw write value (``Admin`` -> ``admin``);
    an unknown display name falls back to lower case.
    ponytail: one card per identity per week assumed (label is the row key);
    split cards collide. Upgrade: key rows on sys_id.
    """
    rows = []
    for card in cards:
        if card.get("week_starts_on") != monday.isoformat():
            continue
        days = [_num(card.get(f)) for f in DAY_FIELDS]
        comments = card.get("comments") or ""
        task = card.get("task.number")
        if task:
            spec = {"taskNumber": task}
            label = row_label(spec, comments)
        else:
            display = card.get("category") or "?"
            spec = {"category": categories.get(display, display.lower())}
            label = display
        rows.append(
            {
                "key": identity_key(spec),
                "label": label,
                **spec,
                "days": days,
                "orig": list(days),
                "description": comments,
                "orig_description": comments,
                "state": card.get("state") or "Pending",
                "remove": False,
            }
        )
    return rows


def new_row(spec: dict, label: str, description: str = "") -> dict:
    """A row with no card behind it yet (``state == "New"``)."""
    return {
        "key": identity_key(spec),
        "label": label,
        **spec,
        "days": [0.0] * 7,
        "orig": [0.0] * 7,
        "description": description,
        "orig_description": description,
        "state": NEW,
        "remove": False,
    }


def grid_data(rows: list[dict]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """(columns, rows) for OwaGridScreen: 7 days + sum, plus a ``per dag`` row."""
    cols = [*DAY_LABELS, "sum"]
    out = []
    per_day = [0.0] * 7
    for row in rows:
        days = [0.0] * 7 if row["remove"] else row["days"]
        per_day = [a + b for a, b in zip(per_day, days)]
        out.append((row["label"], [fmt(v) for v in row["days"]] + [fmt(sum(days))]))
    out.append((SUM_LABEL, [fmt(v) for v in per_day] + [fmt(sum(per_day))]))
    return cols, out


def rows_to_write(rows: list[dict]) -> list[dict]:
    """Dirty, editable rows in the ``owa_swodp.service.validate_write_rows`` shape."""
    out = []
    for row in rows:
        if not is_editable(row) or not is_dirty(row):
            continue
        if row["remove"] and row["state"] == NEW:
            continue  # never written, nothing to remove
        spec = {k: row[k] for k in ("taskNumber", "category") if k in row}
        item = {**spec, "days": list(row["days"]), "description": row["description"]}
        if row["remove"]:
            item["remove"] = True
        out.append(item)
    return out


def diff_lines(rows: list[dict]) -> list[str]:
    """Human summary of what a write would do, one line per dirty row."""
    lines = []
    for row in rows:
        if not is_editable(row) or not is_dirty(row):
            continue
        if row["remove"]:
            if row["state"] != NEW:
                lines.append(f"remove  {row['label']}")
            continue
        if row["state"] == NEW:
            cells = ", ".join(
                f"{d} {fmt(v)}" for d, v in zip(DAY_LABELS, row["days"]) if v
            )
            lines.append(f"create  {row['label']}: {cells or 'all 0'}")
            continue
        changes = [
            f"{d} {fmt(o)}→{fmt(v)}"
            for d, o, v in zip(DAY_LABELS, row["orig"], row["days"])
            if o != v
        ]
        if row["description"] != row["orig_description"]:
            changes.append(f"description: {row['description'][:40]}")
        lines.append(f"update  {row['label']}: {', '.join(changes)}")
    return lines


def round_half(hours: float) -> float:
    """Nearest 0.5, halves up (2.25 -> 2.5), same as cj-weekly-review."""
    return math.floor(hours * 2 + 0.5) / 2


def events_to_hours(
    events: list[dict], monday: date, category_map: dict[str, dict | None]
) -> tuple[dict[str, list[float]], dict[str, dict], dict[str, float]]:
    """Sum normalized calendar events per mapped row identity and weekday.

    Returns ``(hours, specs, unmapped)``: ``hours[key]`` is 7 values rounded
    to the nearest 0.5, ``specs[key]`` the category-map entry, ``unmapped``
    total hours per calendar category that is not in the map. All-day and
    ``showAs == free`` events and events without a category are skipped; a
    category mapped to ``None`` is ignored.
    """
    raw: dict[str, list[float]] = {}
    specs: dict[str, dict] = {}
    unmapped: dict[str, float] = {}
    for ev in events:
        cats = ev.get("categories") or []
        if ev.get("isAllDay") or (ev.get("showAs") or "").lower() == "free" or not cats:
            continue
        try:
            start = datetime.fromisoformat(ev["start"])
            end = datetime.fromisoformat(ev["end"])
        except (KeyError, TypeError, ValueError):
            continue
        idx = (start.date() - monday).days
        if not 0 <= idx < 7:
            continue
        hours = max(0.0, (end - start).total_seconds() / 3600)
        cat = next((c for c in cats if c in category_map), None)
        if cat is None:
            unmapped[cats[0]] = unmapped.get(cats[0], 0.0) + hours
            continue
        spec = category_map[cat]
        if spec is None:
            continue
        key = identity_key(spec)
        specs[key] = spec
        raw.setdefault(key, [0.0] * 7)[idx] += hours
    hours_by_key = {k: [round_half(v) for v in days] for k, days in raw.items()}
    return hours_by_key, specs, unmapped


def merge_fill(
    rows: list[dict], hours: dict[str, list[float]], specs: dict[str, dict]
) -> tuple[int, int]:
    """Fill calendar hours into *rows* in place. Returns ``(filled, kept)``.

    Only empty (0) cells of editable rows are filled; a non-zero cell that
    disagrees with the calendar is kept and counted. Terminal rows are never
    touched. Identities with no row get a new row.
    ponytail: overwrite-behind-confirm from the plan is not built; edit the
    kept cells by hand. Add it when kept > 0 turns out to be common.
    """
    by_key = {r["key"]: r for r in rows}
    filled = kept = 0
    for key, days in hours.items():
        row = by_key.get(key)
        if row is None:
            spec = {k: v for k, v in specs[key].items() if k in ("taskNumber", "category")}
            description = specs[key].get("description", "")
            row = new_row(spec, row_label(spec, description), description)
            rows.append(row)
            by_key[key] = row
        if not is_editable(row):
            continue
        for i, value in enumerate(days):
            if not value or row["days"][i] == value:
                continue
            if row["days"][i] == 0:
                row["days"][i] = value
                filled += 1
            else:
                kept += 1
    return filled, kept
