"""calendar.py — CalendarGrid: the cal screen's calendar view.

A drop-in for :class:`AgendaList` (same ``update_rows`` / ``current_item`` /
``index`` / ``focus_list`` surface and the same Selected/Drilled messages), so
the detail pane, respond and open-in-browser work unchanged. The grid follows
the day range: ``today`` is an hour timeline, ``week`` seven day columns,
``month`` a month grid. A day cursor moves with h/l/←/→ (and j/k by week in
the month grid); the selected event within that day is highlighted. Tab, not
the arrows, switches to the detail pane.
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


def week_grid(
    events: list[dict[str, Any]], day: date, selected: int | None, today: date, cursor: date | None = None
) -> Table:
    monday = _period("week", day)[0]
    by_day = _by_day(events)
    table = Table(expand=True, show_lines=False, pad_edge=False, box=None, padding=(0, 1))
    cells = []
    for n in range(7):
        d = monday + timedelta(days=n)
        head = "reverse" if d == cursor else ("bold" if d == today else "")
        table.add_column(f"{d:%a %d.%m}", header_style=head, ratio=1, overflow="ellipsis")
        cells.append(Group(*[_line(events[i], i == selected) for i in by_day.get(d, [])]) or "")
    table.add_row(*cells)
    return table


def month_grid(
    events: list[dict[str, Any]], day: date, selected: int | None, today: date, cursor: date | None = None
) -> Table:
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
            style = "dim" if d.month != first.month else ""
            if d == today:
                style = "bold"
            if d == cursor:
                style = "reverse"
            head = Text(f" {d.day} " if d == cursor else str(d.day), style=style)
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
    events: list[dict[str, Any]],
    mode: str,
    selected: int | None,
    today: date | None = None,
    cursor: date | None = None,
) -> RenderableType:
    today = today or date.today()
    day = anchor_day(events, mode, today)
    if mode == "week":
        return week_grid(events, day, selected, today, cursor)
    if mode == "month":
        return month_grid(events, day, selected, today, cursor)
    return day_timeline(events, day, selected)


class CalendarGrid(VerticalScroll, can_focus=True):
    """Calendar view with AgendaList's selection surface. See module docstring.

    Keys: h/l/←/→ previous/next day. In week and today view j/k/↓/↑ step
    through the day's events; in the month grid they move a week and J/K step
    through the day's events. g/G first/last event, Enter opens the detail.
    """

    BINDINGS = [
        Binding("h,left", "day(-1)", "Prev day", show=False),
        Binding("l,right", "day(1)", "Next day", show=False),
        Binding("j,down", "down", "Down", show=False),
        Binding("k,up", "up", "Up", show=False),
        Binding("J", "event(1)", "Next event in day", show=False),
        Binding("K", "event(-1)", "Prev event in day", show=False),
        Binding("g", "jump(0)", "First", show=False),
        Binding("G", "jump(-1)", "Last", show=False),
        Binding("enter", "drill", "Open", show=False),
    ]

    def __init__(self, *args: Any, mode: str = "today", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.mode = mode
        self._data: list[dict[str, Any]] = []
        self._by_day: dict[date, list[int]] = {}
        self._index: int | None = None
        self._day: date = date.today()
        self._today: date = date.today()

    def compose(self):  # type: ignore[override]
        yield Static(id="cal-grid-body")

    # --- AgendaList surface -------------------------------------------------

    def update_rows(self, events: list[dict[str, Any]], *, show_date: bool = False) -> None:
        """Show *events*; the cursor starts on the first day from today that has any."""
        self._data = list(events)
        self._by_day = _by_day(self._data)
        lo, hi = self._bounds()
        start = self._today if lo <= self._today <= hi else lo
        self._set_day(next((d for d in sorted(self._by_day) if start <= d <= hi), start))
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
            lo, hi = self._bounds()
            days = [d for d in _days(self._data[value]) if lo <= d <= hi]
            self._day = days[0] if days else self._day
            self._index = value
            self._redraw()

    def focus_list(self) -> None:
        self.focus()

    # --- cursor ------------------------------------------------------------------

    def _bounds(self) -> tuple[date, date]:
        """First and last day the grid shows (the fetched period)."""
        return _period(self.mode, anchor_day(self._data, self.mode, self._today))

    def _day_events(self) -> list[int]:
        return self._by_day.get(self._day, [])

    def _set_day(self, day: date, near: int | None = None) -> None:
        """Move the cursor to *day*; select the event starting nearest *near*
        (minutes since midnight), or the day's first event, or none."""
        self._day = day
        events = self._day_events()
        if not events:
            self._index = None
        elif near is None:
            self._index = events[0]
        else:
            self._index = min(
                events, key=lambda i: abs(_minutes(self._data[i].get("start") or "", 0) - near)
            )

    def _moved(self) -> None:
        self._redraw()
        self.post_message(AgendaItemSelected(self.current_item()))

    def _redraw(self) -> None:
        body = self.query_one("#cal-grid-body", Static)
        cursor = self._day if self.mode != "today" else None
        body.update(render_grid(self._data, self.mode, self._index, self._today, cursor))

    # --- actions --------------------------------------------------------------

    def action_day(self, delta: int) -> None:
        lo, hi = self._bounds()
        day = self._day + timedelta(days=delta)
        if not lo <= day <= hi:  # the grid only holds the fetched period
            return
        cur = self.current_item()
        near = _minutes(cur.get("start") or "", 0) if cur and self.mode == "week" else None
        self._set_day(day, near)
        self._moved()

    def action_event(self, delta: int) -> None:
        events = self._day_events()
        if not events:
            return
        pos = events.index(self._index) if self._index in events else -1
        self._index = events[max(0, min(len(events) - 1, pos + delta))]
        self._moved()

    def action_down(self) -> None:
        if self.mode == "month":
            self.action_day(7)
        else:
            self.action_event(1)

    def action_up(self) -> None:
        if self.mode == "month":
            self.action_day(-7)
        else:
            self.action_event(-1)

    def action_jump(self, where: int) -> None:
        if self._data:
            self.index = where % len(self._data)
            self._moved()

    def action_drill(self) -> None:
        self.post_message(AgendaItemDrilled(self.current_item()))
