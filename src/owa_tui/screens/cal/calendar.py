"""calendar.py — CalendarGrid: the cal screen's calendar view.

A drop-in for :class:`AgendaList` (same ``update_rows`` / ``current_item`` /
``index`` / ``focus_list`` surface and the same Selected/Drilled messages), so
the detail pane, respond and open-in-browser work unchanged. The grid follows
the day range: ``today`` is an hour timeline, ``week`` seven day columns,
``month`` a month grid. j/k step through events in time order; the selected
event is highlighted.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta
from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from owa_tui.screens.cal.agenda import AgendaItemDrilled, AgendaItemSelected

SELECTED = "reverse"
MONTH_CELL_LINES = 3  # ponytail: events past this show as "+N"; the selected one is always shown


def _day(event: dict[str, Any]) -> date | None:
    try:
        return date.fromisoformat((event.get("start") or "")[:10])
    except ValueError:
        return None


def _days(event: dict[str, Any]) -> list[date]:
    """Days an event is drawn on: all-day events on each day of their span."""
    first = _day(event)
    if first is None:
        return []
    if not event.get("isAllDay"):
        return [first]
    try:
        last = date.fromisoformat((event.get("end") or "")[:10]) - timedelta(days=1)
    except ValueError:
        last = first
    return [first + timedelta(days=n) for n in range(max(0, (last - first).days) + 1)]


def _line(event: dict[str, Any], selected: bool) -> Text:
    when = "all-day" if event.get("isAllDay") else (event.get("start") or "")[11:16]
    who = f"{event['_profile']} " if event.get("_profile") else ""  # merged (-A) mode
    text = Text(f"{when} {who}{event.get('subject') or '(no subject)'}", no_wrap=True, overflow="ellipsis")
    if selected:
        text.stylize(SELECTED)
    return text


def _by_day(events: list[dict[str, Any]]) -> dict[date, list[int]]:
    out: dict[date, list[int]] = {}
    for i, ev in enumerate(events):
        for d in _days(ev):
            out.setdefault(d, []).append(i)
    return out


def anchor_day(events: list[dict[str, Any]], mode: str, today: date) -> date:
    """*today*, unless no event falls in today's period (fixtures): then the first event's day."""
    days = [d for ev in events for d in _days(ev)]
    if not days or any(_period(mode, today)[0] <= d <= _period(mode, today)[1] for d in days):
        return today
    return min(days)


def _period(mode: str, day: date) -> tuple[date, date]:
    if mode == "week":
        monday = day - timedelta(days=day.weekday())
        return monday, monday + timedelta(days=6)
    if mode == "month":
        first = day.replace(day=1)
        return first, first.replace(day=_cal.monthrange(day.year, day.month)[1])
    return day, day


def week_grid(events: list[dict[str, Any]], day: date, selected: int | None, today: date) -> Table:
    monday = _period("week", day)[0]
    by_day = _by_day(events)
    table = Table(expand=True, show_lines=False, pad_edge=False, box=None, padding=(0, 1))
    cells = []
    for n in range(7):
        d = monday + timedelta(days=n)
        table.add_column(f"{d:%a %d.%m}", style="bold" if d == today else None, ratio=1, overflow="ellipsis")
        cells.append(Group(*[_line(events[i], i == selected) for i in by_day.get(d, [])]) or "")
    table.add_row(*cells)
    return table


def month_grid(events: list[dict[str, Any]], day: date, selected: int | None, today: date) -> Table:
    first, last = _period("month", day)
    by_day = _by_day(events)
    table = Table(expand=True, show_lines=True, pad_edge=False, padding=(0, 1))
    for name in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        table.add_column(name, ratio=1, overflow="ellipsis")
    start = first - timedelta(days=first.weekday())
    while start <= last:
        row = []
        for n in range(7):
            d = start + timedelta(days=n)
            head = Text(str(d.day), style="bold" if d == today else ("dim" if d.month != first.month else ""))
            idx = by_day.get(d, [])
            shown = idx[:MONTH_CELL_LINES]
            if selected in idx and selected not in shown:
                shown = [*shown[:-1], selected]
            lines = [_line(events[i], i == selected) for i in shown]
            if len(idx) > len(shown):
                lines.append(Text(f"+{len(idx) - len(shown)}", style="dim"))
            row.append(Group(head, *lines))
        table.add_row(*row)
        start += timedelta(days=7)
    return table


def _minutes(ts: str, default: int) -> int:
    """Minutes since midnight of an ISO timestamp's time part."""
    try:
        return int(ts[11:13]) * 60 + int(ts[14:16])
    except ValueError:
        return default


def day_timeline(events: list[dict[str, Any]], day: date, selected: int | None) -> Text:
    todays = [i for i, ev in enumerate(events) if day in _days(ev)]
    all_day = [i for i in todays if events[i].get("isAllDay")]
    timed = [
        (i, _minutes(events[i].get("start") or "", 8 * 60), _minutes(events[i].get("end") or "", 17 * 60))
        for i in todays
        if not events[i].get("isAllDay")
    ]
    lo = min([8, *(s // 60 for _, s, _ in timed)])
    hi = max([17, *((e - 1) // 60 for _, _, e in timed)])
    out = Text()
    for i in all_day:
        out.append("all-day │ ")
        out.append_text(_line(events[i], i == selected))
        out.append("\n")
    for hour in range(lo, hi + 1):
        out.append(f"{hour:02d}:00   │ ", style="dim")
        parts = [_line(events[i], i == selected) for i, s, _ in timed if s // 60 == hour]
        parts += [  # still running from an earlier hour
            Text(f"┆ {events[i].get('subject') or ''}", style="dim", no_wrap=True)
            for i, s, e in timed
            if s // 60 < hour and hour * 60 < e
        ]
        for n, part in enumerate(parts):
            if n:
                out.append("  ")
            out.append_text(part)
        out.append("\n")
    return out


def render_grid(
    events: list[dict[str, Any]], mode: str, selected: int | None, today: date | None = None
) -> RenderableType:
    today = today or date.today()
    day = anchor_day(events, mode, today)
    if mode == "week":
        return week_grid(events, day, selected, today)
    if mode == "month":
        return month_grid(events, day, selected, today)
    return day_timeline(events, day, selected)


class CalendarGrid(VerticalScroll, can_focus=True):
    """Calendar view with AgendaList's selection surface. See module docstring."""

    BINDINGS = [
        Binding("j,down", "move(1)", "Next", show=False),
        Binding("k,up", "move(-1)", "Prev", show=False),
        Binding("g", "jump(0)", "First", show=False),
        Binding("G", "jump(-1)", "Last", show=False),
        Binding("l,right,enter", "drill", "Open", show=False),
    ]

    def __init__(self, *args: Any, mode: str = "today", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.mode = mode
        self._data: list[dict[str, Any]] = []
        self._index: int | None = None

    def compose(self):  # type: ignore[override]
        yield Static(id="cal-grid-body")

    # --- AgendaList surface -------------------------------------------------

    def update_rows(self, events: list[dict[str, Any]], *, show_date: bool = False) -> None:
        self._data = list(events)
        self._index = 0 if self._data else None
        self._redraw()

    def current_item(self) -> dict[str, Any] | None:
        return self._data[self._index] if self._index is not None else None

    @property
    def item_count(self) -> int:
        return len(self._data)

    @property
    def index(self) -> int | None:
        return self._index

    @index.setter
    def index(self, value: int | None) -> None:
        if value is not None and 0 <= value < len(self._data):
            self._index = value
            self._redraw()

    def focus_list(self) -> None:
        self.focus()

    # --- actions --------------------------------------------------------------

    def _redraw(self) -> None:
        body = self.query_one("#cal-grid-body", Static)
        body.update(render_grid(self._data, self.mode, self._index))

    def action_move(self, delta: int) -> None:
        if self._index is None:
            return
        self._index = max(0, min(len(self._data) - 1, self._index + delta))
        self._redraw()
        self.post_message(AgendaItemSelected(self.current_item()))

    def action_jump(self, where: int) -> None:
        if self._data:
            self._index = where % len(self._data)
            self._redraw()
            self.post_message(AgendaItemSelected(self.current_item()))

    def action_drill(self) -> None:
        self.post_message(AgendaItemDrilled(self.current_item()))
