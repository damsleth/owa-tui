"""screen.py — SwodpScreen: one week of SWODP time cards as an editable grid.

Rows are cards (task or category), columns are weekdays plus a sum, and a
``per dag`` row sums each day. Edits stay local (bold yellow) until ``w``
writes them through ``owa_swodp.service.write_week`` after a confirm. Only
Pending (or new) rows are editable; Submitted/Approved/Processed are dimmed.
There is deliberately no submit binding: submitting stays in the SWODP portal
or ``owa-swodp submit``.

Config (``~/.config/owa-tui/tui.json``, key ``swodp``, seeded on first run)::

    {"instance": "prod", "cal_profile": "swon", "category_map": {...}}

``category_map`` maps an Outlook category to a row identity for ``c``
(fill from calendar); ``null`` ignores the category.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from typing import Any

from textual import work
from textual.binding import Binding
from textual.widgets import DataTable, Label

from owa_tui import fixtures
from owa_tui.screens.base.grid import GRID_BINDINGS, GridData, OwaGridScreen
from owa_tui.screens.swodp import adapter, plan

TASK_RE = re.compile(r"^T[0-9A-Z]{5,30}$")

HELP = (
    "hjkl move  Enter/i edit  x zero  a add row  e description  D remove row  "
    "c fill from calendar  w write  [ ] week  t this week  r reload  q quit"
)


def _settings() -> dict[str, Any]:
    from owa_tui import app_config  # noqa: PLC0415

    saved = app_config.load()
    data = saved.get("swodp") or {}
    return {
        "instance": data.get("instance") or "prod",
        "cal_profile": data.get("cal_profile") or "swon",
        "category_map": data.get("category_map") or dict(plan.DEFAULT_CATEGORY_MAP),
        "_seeded": "swodp" in saved,
    }


def _fixture_monday() -> date | None:
    # ponytail: fixture cards are for a fixed past week; open on the newest.
    cards = fixtures.load("swodp") or []
    weeks = [c["week_starts_on"] for c in cards if c.get("week_starts_on")]
    return date.fromisoformat(max(weeks)) if weeks else None


class SwodpScreen(OwaGridScreen):
    """Editable SWODP week grid. See module docstring."""

    BINDINGS = GRID_BINDINGS + [  # type: ignore[assignment]
        Binding("i", "edit_cell", "Edit"),
        Binding("x", "zero_cell", "Zero", show=False),
        Binding("a", "add_row", "Add row"),
        Binding("e", "edit_description", "Description", show=False),
        Binding("D", "toggle_remove", "Remove row", show=False),
        Binding("c", "fill_calendar", "From calendar"),
        Binding("w", "write", "Write"),
        Binding("left_square_bracket", "prev_week", "Prev week", show=False),
        Binding("right_square_bracket", "next_week", "Next week", show=False),
        Binding("t", "this_week", "This week", show=False),
    ]

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        week_start: date | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            config=config, tool_name="swodp", audience="outlook", title="Timesheet (SWODP)", **kwargs
        )
        self._settings = _settings()
        self._instance: str = self._settings["instance"]
        self._monday = plan.monday_of(
            week_start or (fixtures.enabled() and _fixture_monday()) or date.today()
        )
        self._session: Any = None
        self._categories: dict[str, str] | None = None
        self._plan: list[dict] = []
        # (monday, rows) built in the worker, swapped in on the UI thread.
        self._incoming: tuple[date, list[dict]] | None = None
        self._range_cards: list[dict] = []
        self._by_label: dict[str, dict] = {}
        self._note = ""

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._seed_config()
        super().on_mount()

    def _seed_config(self) -> None:
        """Write the default swodp section to tui.json once, so the map is editable."""
        if self._settings["_seeded"] or fixtures.enabled() or self.app.is_headless:
            return
        from owa_tui import app_config  # noqa: PLC0415

        data = app_config.load()
        data["swodp"] = {k: v for k, v in self._settings.items() if not k.startswith("_")}
        app_config.save(data)

    async def fetch_grid(self, search: str = "") -> GridData:
        # Runs in the base's worker thread: blocking calls are fine here.
        if self._session is None:
            self.app.call_from_thread(
                lambda: setattr(self, "_status", f"capturing SWODP session ({self._instance})…")
            )
            self._session = adapter.capture(self._instance)
        try:
            cards = adapter.week(self._session, self._monday, self._instance)
        except adapter.SwodpAuthError:
            self._session = None  # r re-captures
            raise
        if self._categories is None:
            self._categories = adapter.categories(self._session)
        discarded = sum(plan.is_dirty(r) for r in self._plan)
        if discarded and not self._note:
            self._note = f"discarded {discarded} unwritten row(s)"
        monday = self._monday
        self._range_cards = cards
        self._incoming = (monday, plan.cards_to_rows(cards, monday, self._categories))
        return plan.grid_data(self._incoming[1])

    def _apply_grid(self, col_labels: list[str], rows: list[tuple[str, list[str]]]) -> None:
        if self._incoming is not None:
            monday, rows_in = self._incoming
            self._incoming = None
            if monday == self._monday:  # a fetch for a week we already left is dropped
                self._plan = rows_in
        # Always render from self._plan so overlapping fetches ([[[) can't mix
        # one week's cells with another week's row styling.
        col_labels, rows = plan.grid_data(self._plan)
        self._by_label = {r["label"]: r for r in self._plan}
        tbl = self._table()
        coord = tbl.cursor_coordinate
        super()._apply_grid(col_labels, rows)
        if rows:
            tbl.move_cursor(row=min(coord.row, len(rows) - 1), column=max(1, coord.column))
        self.query_one("#owa-grid-breadcrumb", Label).update(
            plan.week_title(self._monday, self._instance)
        )
        dirty = sum(plan.is_dirty(r) for r in self._plan)
        summary = f"{len(self._plan)} kort · {rows[-1][1][-1] if rows else 0} timer"
        if dirty:
            summary += f" · {dirty} unwritten (w to write)"
        self._status = f"{self._note} · {summary}" if self._note else summary
        self._note = ""

    def _render_plan(self, note: str = "") -> None:
        """Re-render from ``self._plan`` after a local edit, keeping the cursor."""
        self._note = note
        self._apply_grid(*plan.grid_data(self._plan))

    def _table(self) -> DataTable:
        return self.query_one("#owa-grid-table", DataTable)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
        if row_label == plan.SUM_LABEL or col_label == "sum":
            return "bold"
        row = self._by_label.get(row_label)
        if row is not None:
            if row["remove"]:
                return "strike dim"
            if not plan.is_editable(row):
                return "dim"
            i = plan.DAY_LABELS.index(col_label)
            if row["days"][i] != row["orig"][i]:
                return "bold yellow"
        return "dim" if value == "0" else None

    # ------------------------------------------------------------------
    # Cursor helpers
    # ------------------------------------------------------------------

    def _cursor(self) -> tuple[dict | None, int | None]:
        coord = self._table().cursor_coordinate
        if coord.row >= len(self._plan):
            return None, None  # the per-dag row
        day = coord.column - 1 if 1 <= coord.column <= 7 else None
        return self._plan[coord.row], day

    def _editable_row(self) -> dict | None:
        row, _ = self._cursor()
        if row is None:
            self._status = "not an editable row"
        elif not plan.is_editable(row):
            self._status = f"{row['label']} is {row['state']} — read-only"
        elif row["remove"]:
            self._status = f"{row['label']} is marked for removal (D to undo)"
        else:
            return row
        return None

    def _editable_cell(self) -> tuple[dict, int] | None:
        row = self._editable_row()
        if row is None:
            return None
        _, day = self._cursor()
        if day is None:
            self._status = "move to a day column (man–søn) to edit"
            return None
        return row, day

    def _prompt(self, text: str, placeholder: str, callback: Any) -> None:
        from owa_tui.screens.base.screen import _SearchModal  # noqa: PLC0415

        self.app.push_screen(
            _SearchModal(text, placeholder, hint="Enter to confirm  Esc to cancel"), callback
        )

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _show_cell_detail(self, row: int, column: int) -> None:
        """Enter on a day cell of an editable row edits it; else show detail."""
        if row < len(self._plan) and 1 <= column <= 7 and plan.is_editable(self._plan[row]):
            self.action_edit_cell()
        else:
            super()._show_cell_detail(row, column)

    def cell_detail(self, row_label: str, col_label: str, value: str) -> str:
        row = self._by_label.get(row_label)
        if row is None:
            return super().cell_detail(row_label, col_label, value)
        return f"{row['label']} · {row['state']} · {row['description'] or '(no description)'}"

    def action_edit_cell(self) -> None:
        target = self._editable_cell()
        if target is None:
            return
        row, day = target

        def _done(value: str | None) -> None:
            if value is None:
                return
            try:
                hours = float(value.replace(",", "."))
            except ValueError:
                self._status = f"not a number: {value!r}"
                return
            if not 0 <= hours <= 24 or (hours * 4) % 1:
                self._status = "hours must be 0–24 in steps of 0.25"
                return
            row["days"][day] = hours
            self._render_plan()

        current = plan.fmt(row["days"][day])
        self._prompt(
            f"{row['label']} · {plan.DAY_LABELS[day]} (now {current}; 0–24, step 0.25):",
            current,
            _done,
        )

    def action_zero_cell(self) -> None:
        target = self._editable_cell()
        if target is not None:
            row, day = target
            row["days"][day] = 0.0
            self._render_plan()

    def action_toggle_remove(self) -> None:
        row = self._cursor()[0]
        if row is None or not plan.is_editable(row):
            self._editable_row()  # sets the reason
            return
        if row["state"] == plan.NEW:
            self._plan.remove(row)
            self._render_plan(f"dropped new row {row['label']}")
            return
        row["remove"] = not row["remove"]
        self._render_plan(f"{row['label']}: {'remove on write' if row['remove'] else 'kept'}")

    def action_edit_description(self) -> None:
        row = self._editable_row()
        if row is None:
            return

        def _done(value: str | None) -> None:
            if value and value.strip():
                row["description"] = value.strip()
                if "taskNumber" in row:  # the "Kort" prefix comes from the description
                    row["label"] = plan.row_label(row, row["description"])
                self._render_plan(f"description set for {row['label']}")

        self._prompt(
            f"Description for {row['label']} (now: {row['description'][:60] or 'empty'}):",
            "description…",
            _done,
        )

    def _known_rows(self) -> tuple[list[str], dict[str, str]]:
        """Task numbers seen in the card range, and categories (display -> raw)."""
        tasks = sorted({c["task.number"] for c in self._range_cards if c.get("task.number")})
        return tasks, dict(self._categories or {})

    def _latest_description(self, key: str) -> str:
        """Newest description used for *key* anywhere in the card range."""
        cats = self._categories or {}
        found = ""
        for card in sorted(self._range_cards, key=lambda c: c.get("week_starts_on") or ""):
            display = card.get("category") or ""
            card_key = card.get("task.number") or f"category:{cats.get(display, display.lower())}"
            if card_key == key and card.get("comments"):
                found = card["comments"]
        return found

    def action_add_row(self) -> None:
        tasks, cats = self._known_rows()

        def _done(value: str | None) -> None:
            text = (value or "").strip()
            if not text:
                return
            by_display = {k.lower(): v for k, v in cats.items()}
            if TASK_RE.fullmatch(text.upper()):
                spec = {"taskNumber": text.upper()}
            elif text.lower() in by_display:
                spec = {"category": by_display[text.lower()]}
            elif text.lower() in {v.lower() for v in cats.values()}:
                spec = {"category": text.lower()}
            else:
                self._status = f"unknown row {text!r}: use a task number (T…) or a category"
                return
            key = plan.identity_key(spec)
            if any(r["key"] == key for r in self._plan):
                # ponytail: a second card beside a Submitted one ("new": true) is not
                # supported; use owa-swodp write for that case.
                self._status = f"{text} is already in this week"
                return
            description = self._latest_description(key)
            row = plan.new_row(spec, plan.row_label(spec, description), description)
            self._plan.append(row)
            hint = "" if description else " — press e to set a description"
            self._render_plan(f"added {row['label']}{hint}")

        known = ", ".join([*tasks, *cats]) or "none seen"
        self._prompt(f"Add row: task number or category (known: {known})", "T… or category", _done)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def action_write(self) -> None:
        rows = plan.rows_to_write(self._plan)
        if not rows:
            self._status = "nothing to write"
            return
        try:
            adapter.validate(rows)
        except Exception as exc:  # noqa: BLE001 — UsageError names the row number
            m = re.search(r"row (\d+)", str(exc))
            who = rows[int(m.group(1)) - 1] if m else {}
            label = who.get("taskNumber") or who.get("category") or ""
            self._status = f"cannot write {label}: {exc}".replace("  ", " ")
            return
        lines = plan.diff_lines(self._plan)
        text = "\n".join(
            [
                f"Write to SWODP, {plan.week_title(self._monday, self._instance)}:",
                *lines,
                "",
                "Type y and Enter to write (cards stay Pending; nothing is submitted).",
            ]
        )

        def _done(value: str | None) -> None:
            if (value or "").strip().lower() in ("y", "yes"):
                self._write(rows)
            else:
                self._status = "write cancelled"

        self._prompt(text, "y", _done)

    @work(thread=True, exclusive=True, group="swodp-write")
    def _write(self, rows: list[dict]) -> None:
        self.app.call_from_thread(lambda: setattr(self, "_status", "writing…"))
        try:
            if self._session is None:
                self._session = adapter.capture(self._instance)
            results = adapter.write(self._session, self._monday, rows)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, adapter.SwodpAuthError):
                self._session = None
            msg = f"write failed: {exc}"
            self.app.call_from_thread(lambda: setattr(self, "_status", msg))
            return
        counts = Counter(r.get("action", "?") for r in results)
        note = ", ".join(f"{n} {action}" for action, n in counts.items())
        problems = [
            f"{r.get('taskNumber')}: {r['detail']}" for r in results if r.get("detail")
        ]
        if problems:
            note += " — " + "; ".join(problems)
        if fixtures.enabled():
            note += " (fixture dry-run)"

        def _after() -> None:
            self._plan = []  # written: nothing to discard on reload
            self._note = note
            self._fetch_grid()

        self.app.call_from_thread(_after)

    # ------------------------------------------------------------------
    # Fill from calendar
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True, group="swodp-fill")
    def action_fill_calendar(self) -> None:
        profile = self._settings["cal_profile"]
        self.app.call_from_thread(
            lambda: setattr(self, "_status", f"reading calendar ({profile})…")
        )
        try:
            events = adapter.calendar_events(self._config, profile, self._monday)
        except Exception as exc:  # noqa: BLE001
            msg = f"calendar: {exc}"
            self.app.call_from_thread(lambda: setattr(self, "_status", msg))
            return
        self.app.call_from_thread(self._merge_calendar, events)

    def _merge_calendar(self, events: list[dict]) -> None:
        hours, specs, unmapped = plan.events_to_hours(
            events, self._monday, self._settings["category_map"]
        )
        filled, kept = plan.merge_fill(self._plan, hours, specs)
        note = f"calendar: {filled} cell(s) filled"
        if kept:
            note += f", {kept} kept (already filled; edit by hand)"
        if unmapped:
            cats = ", ".join(f"{c} {plan.fmt(h)}h" for c, h in sorted(unmapped.items()))
            note += f", unmapped: {cats} (add to swodp.category_map in tui.json)"
        self._render_plan(note)

    # ------------------------------------------------------------------
    # Week navigation
    # ------------------------------------------------------------------

    def _go(self, monday: date) -> None:
        self._monday = monday
        self._fetch_grid()

    def action_prev_week(self) -> None:
        self._go(self._monday - timedelta(weeks=1))

    def action_next_week(self) -> None:
        self._go(self._monday + timedelta(weeks=1))

    def action_this_week(self) -> None:
        self._go(plan.monday_of(date.today()))

    def handle_menu_result(self, result: str) -> None:
        if result == "help":
            self._status = HELP
        else:
            super().handle_menu_result(result)

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return (f"Timesheet (SWODP) — {self._instance} · calendar {self._settings['cal_profile']}", [])

