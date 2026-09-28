"""screen.py — SwodpScreen: one week of SWODP time cards as an editable grid.

Rows are cards (task or category), columns are weekdays plus a sum, and a
``per dag`` row sums each day. Edits stay local (bold yellow) until ``w``
writes them through ``owa_swodp.service.write_week`` after a confirm. Only
Pending (or new) rows are editable; Submitted/Approved/Processed are dimmed.
There is deliberately no submit binding: submitting stays in the SWODP portal
or ``owa-swodp submit``.

Config (``~/.config/owa-tui/tui.json``, key ``swodp``, seeded on first run)::

    {"instance": "prod", "cal_profile": "swon", "default_week": "current",
     "category_map": {...}}

``default_week`` (``previous`` | ``current`` | ``next``) is the week the screen
opens on; ``weeks_shown`` (1–4) stacks that many weeks, ending at it, one block
each (title row, cards, ``per dag``). Both are also in Esc → Settings. The
block under the cursor is the active week: edits, ``a``, ``c`` and ``w`` act on
it. Weeks that stay in view keep unwritten edits across ``H``/``L``.

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

# default_week setting -> week offset from the current week.
DEFAULT_WEEKS = {"previous": -1, "current": 0, "next": 1}
# ponytail: capped at 4 — one week_cards call spans ±3 weeks around the anchor.
WEEKS_SHOWN = (1, 2, 3, 4)

HELP = (
    "hjkl move  Enter/i edit  x zero  a add row  e description  D remove row  "
    "c fill from calendar  w write  H/L or [ ] week  t this week  r reload  q quit"
)


def _settings() -> dict[str, Any]:
    from owa_tui import app_config  # noqa: PLC0415

    saved = app_config.load()
    data = saved.get("swodp") or {}
    return {
        "instance": data.get("instance") or "prod",
        "cal_profile": data.get("cal_profile") or "swon",
        "default_week": data.get("default_week") if data.get("default_week") in DEFAULT_WEEKS else "current",
        "weeks_shown": data.get("weeks_shown") if data.get("weeks_shown") in WEEKS_SHOWN else 1,
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
        # [ ] are Alt+8/9 on a Norwegian Mac layout; H/L sit next to h/l.
        Binding("H", "prev_week", "Prev week", show=False),
        Binding("L", "next_week", "Next week", show=False),
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
        # The anchor is the navigation week (last block); _monday/_plan are the
        # active week, i.e. the block the cursor is in.
        self._anchor = plan.monday_of(
            week_start
            or (fixtures.enabled() and _fixture_monday())
            or date.today() + timedelta(weeks=DEFAULT_WEEKS[self._settings["default_week"]])
        )
        self._monday = self._anchor
        self._weeks_shown: int = self._settings["weeks_shown"]
        self._session: Any = None
        self._categories: dict[str, str] | None = None
        self._plans: dict[date, list[dict]] = {}
        self._plan: list[dict] = []
        # {monday: rows} built in the worker, merged in on the UI thread.
        self._incoming: dict[date, list[dict]] | None = None
        self._range_cards: list[dict] = []
        # One (monday, plan index | None) per table row; None = title/per dag row.
        self._row_map: list[tuple[date, int | None]] = []
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
        anchor = self._anchor
        try:
            cards = adapter.week(self._session, anchor, self._instance)  # ±3 weeks
        except adapter.SwodpAuthError:
            self._session = None  # r re-captures
            raise
        if self._categories is None:
            self._categories = adapter.categories(self._session)
        self._range_cards = cards
        self._incoming = {
            m: plan.cards_to_rows(cards, m, self._categories) for m in self._window(anchor)
        }
        return [], []  # _apply_grid renders from self._plans

    def _window(self, anchor: date | None = None) -> list[date]:
        """Mondays shown, oldest first, ending at *anchor* (default: the current one)."""
        anchor = anchor or self._anchor
        return [anchor - timedelta(weeks=n) for n in range(self._weeks_shown - 1, -1, -1)]

    def _drop_weeks(self, weeks: list[date]) -> None:
        """Forget loaded weeks; note how many unwritten rows that throws away."""
        discarded = sum(plan.is_dirty(r) for m in weeks for r in self._plans.pop(m, []))
        if discarded and not self._note:
            self._note = f"discarded {discarded} unwritten row(s)"

    def _apply_grid(self, _cols: Any = None, _rows: Any = None) -> None:
        # Merge only weeks still in view and not loaded yet: overlapping fetches
        # ([[[) can't clobber local edits or render a week we already left.
        incoming, self._incoming = self._incoming or {}, None
        window = self._window()
        for m in window:
            if m not in self._plans and m in incoming:
                self._plans[m] = incoming[m]
        tbl = self._table()
        coord = tbl.cursor_coordinate
        was = self._row_map[coord.row] if 0 <= coord.row < len(self._row_map) else None
        self._render_table(window)
        if not self._row_map:
            return
        if was in self._row_map:
            row = self._row_map.index(was)
        else:  # first card row of the anchor week (or its per dag row)
            row = next(
                (i for i, (m, _) in enumerate(self._row_map) if m == self._anchor),
                len(self._row_map) - 1,
            )
            if self._weeks_shown > 1 and self._row_map[row][1] is None and row + 1 < len(self._row_map):
                row += 1  # skip the title row
        tbl.move_cursor(row=row, column=max(1, coord.column))
        self._activate(self._row_map[row][0])

    def _render_table(self, window: list[date]) -> None:
        tbl = self._table()
        tbl.clear(columns=True)
        cols = [*plan.DAY_LABELS, "sum"]
        tbl.add_column("", key="_row_label")
        for c in cols:
            tbl.add_column(c, key=c)
        self._col_labels, self._rows, self._row_map = cols, [], []
        for m in window:
            rows = self._plans.get(m)
            if rows is None:
                continue  # still loading
            if self._weeks_shown > 1:
                title = f"Uke {m.isocalendar()[1]} · {m:%d.%m}–{m + timedelta(days=6):%d.%m}"
                tbl.add_row(f"[bold]{title}[/bold]", *[""] * len(cols))
                self._rows.append((title, [""] * len(cols)))
                self._row_map.append((m, None))
            for i, (label, cells) in enumerate(plan.grid_data(rows)[1]):
                row = rows[i] if i < len(rows) else None
                styled = []
                for c, v in zip(cols, cells):
                    st = self._style(row, label, c, v)
                    styled.append(f"[{st}]{v}[/{st}]" if st else v)
                tbl.add_row(label, *styled)
                self._rows.append((label, cells))
                self._row_map.append((m, i if row is not None else None))

    def _activate(self, monday: date) -> None:
        """Make *monday*'s block the active week: breadcrumb and status follow it."""
        self._monday = monday
        self._plan = self._plans.get(monday, [])
        self.query_one("#owa-grid-breadcrumb", Label).update(
            plan.week_title(monday, self._instance)
        )
        dirty = sum(plan.is_dirty(r) for r in self._plan)
        total = plan.grid_data(self._plan)[1][-1][1][-1]
        summary = f"{len(self._plan)} kort · {total} timer"
        if dirty:
            summary += f" · {dirty} unwritten (w to write)"
        self._status = f"{self._note} · {summary}" if self._note else summary
        self._note = ""

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        row = event.coordinate.row
        if 0 <= row < len(self._row_map) and self._row_map[row][0] != self._monday:
            self._activate(self._row_map[row][0])

    def _render_plan(self, note: str = "") -> None:
        """Re-render after a local edit, keeping the cursor."""
        self._note = note
        self._apply_grid()

    def _table(self) -> DataTable:
        return self.query_one("#owa-grid-table", DataTable)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def cell_style(self, row_label: str, col_label: str, value: str) -> str | None:
        if row_label == plan.SUM_LABEL or col_label == "sum":
            return "bold"
        return "dim" if value == "0" else None

    def _style(self, row: dict | None, label: str, col_label: str, value: str) -> str | None:
        """cell_style, plus per-row state (removed, read-only, dirty) for card rows."""
        if row is not None and col_label != "sum":
            if row["remove"]:
                return "strike dim"
            if not plan.is_editable(row):
                return "dim"
            i = plan.DAY_LABELS.index(col_label)
            if row["days"][i] != row["orig"][i]:
                return "bold yellow"
        return self.cell_style(label, col_label, value)

    # ------------------------------------------------------------------
    # Cursor helpers
    # ------------------------------------------------------------------

    def _cursor(self) -> tuple[dict | None, int | None]:
        coord = self._table().cursor_coordinate
        m, i = self._row_map[coord.row] if 0 <= coord.row < len(self._row_map) else (None, None)
        if i is None:
            return None, None  # a title or per-dag row
        day = coord.column - 1 if 1 <= coord.column <= 7 else None
        return self._plans[m][i], day

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
        m, i = self._row_map[row] if 0 <= row < len(self._row_map) else (None, None)
        if i is None:
            super()._show_cell_detail(row, column)
            return
        card = self._plans[m][i]
        if 1 <= column <= 7 and plan.is_editable(card):
            self.action_edit_cell()
        else:
            self._status = (
                f"{card['label']} · {card['state']} · {card['description'] or '(no description)'}"
            )

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
        monday = self._monday
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
                self._write(monday, rows)
            else:
                self._status = "write cancelled"

        self._prompt(text, "y", _done)

    @work(thread=True, exclusive=True, group="swodp-write")
    def _write(self, monday: date, rows: list[dict]) -> None:
        self.app.call_from_thread(lambda: setattr(self, "_status", "writing…"))
        try:
            if self._session is None:
                self._session = adapter.capture(self._instance)
            results = adapter.write(self._session, monday, rows)
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
            self._plans.pop(monday, None)  # written: reload that week, nothing to discard
            self._note = note
            self._fetch_grid()

        self.app.call_from_thread(_after)

    # ------------------------------------------------------------------
    # Fill from calendar
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True, group="swodp-fill")
    def action_fill_calendar(self) -> None:
        profile = self._settings["cal_profile"]
        monday = self._monday
        self.app.call_from_thread(
            lambda: setattr(self, "_status", f"reading calendar ({profile})…")
        )
        try:
            events = adapter.calendar_events(self._config, profile, monday)
        except Exception as exc:  # noqa: BLE001
            msg = f"calendar: {exc}"
            self.app.call_from_thread(lambda: setattr(self, "_status", msg))
            return
        self.app.call_from_thread(self._merge_calendar, events, monday)

    def _merge_calendar(self, events: list[dict], monday: date) -> None:
        hours, specs, unmapped = plan.events_to_hours(
            events, monday, self._settings["category_map"]
        )
        rows = self._plans.get(monday)
        if rows is None:
            self._status = "calendar: that week is no longer shown"
            return
        filled, kept = plan.merge_fill(rows, hours, specs)
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

    def _go(self, anchor: date) -> None:
        self._anchor = self._monday = anchor
        self._drop_weeks([m for m in self._plans if m not in self._window()])
        self._fetch_grid()

    def action_refresh(self) -> None:
        self._drop_weeks(list(self._plans))
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
        return (
            f"Timesheet (SWODP) — {self._instance} · calendar {self._settings['cal_profile']}",
            [("default_week", "Default week"), ("weeks_shown", "Weeks shown")],
        )

    def action_open_menu(self) -> None:
        from types import SimpleNamespace  # noqa: PLC0415

        from owa_tui.settings_cycle import cycle_value  # noqa: PLC0415
        from owa_tui.widgets.settings_overlay import SettingsOverlay  # noqa: PLC0415

        title, fields = self.menu_config()
        overlay = SettingsOverlay(
            title_lines=[title],
            top_items=[("Resume", "resume"), ("Settings", "settings"), ("Help", "help"), ("Quit", "quit")],
            settings_fields=fields,
            settings=SimpleNamespace(
                default_week=self._settings["default_week"], weeks_shown=self._weeks_shown
            ),
            cycle_fn=lambda st, f, d: SimpleNamespace(
                **{**vars(st), f: cycle_value(getattr(st, f), options[f], d)}
            ),
            on_change=lambda f, st: self._save_setting(f, getattr(st, f)),
        )
        options = {"default_week": tuple(DEFAULT_WEEKS), "weeks_shown": WEEKS_SHOWN}
        self.app.push_screen(overlay, self.handle_menu_result)

    def _save_setting(self, key: str, value: Any) -> None:
        """Persist a swodp setting to tui.json. weeks_shown applies live;
        default_week takes effect on the next open."""
        self._settings[key] = value
        if key == "weeks_shown":
            self._weeks_shown = value
            self._drop_weeks([m for m in self._plans if m not in self._window()])
            self._fetch_grid()
        if fixtures.enabled():
            return
        from owa_tui import app_config  # noqa: PLC0415

        data = app_config.load()
        data.setdefault("swodp", {})[key] = value
        app_config.save(data)

