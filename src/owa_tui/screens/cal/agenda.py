"""AgendaList widget — scrollable calendar event list."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

# ---------------------------------------------------------------------------
# Row render helpers
# ---------------------------------------------------------------------------

_RESPONSE_LABEL: dict[str, str] = {
    "accepted": "accepted",
    "declined": "declined",
    "tentativelyaccepted": "tentative",
    "tentative": "tentative",
    "notresponded": "no reply",
    "none": "no reply",
    "organizer": "organizer",
}


def _weekday_date(start: str) -> str:
    """Return a 9-char weekday+date prefix like ``'Thu 06-05'``."""
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(start)
        return dt.strftime("%a %m-%d")
    except Exception:
        return "         "


def render_row(event: dict[str, Any], width: int, *, show_date: bool = False) -> str:
    """Render a single agenda row to a string capped at *width* chars.

    Ported verbatim from ``owa_cal.tui.render_row``.
    """
    if width < 1:
        width = 1

    start: str = event.get("start") or ""
    end: str = event.get("end") or ""
    subject: str = event.get("subject") or ""
    location: str = event.get("location") or ""
    is_all_day: bool = bool(event.get("isAllDay"))

    # Build time column (12 chars)
    if is_all_day:
        time_col = "all-day     "
    else:
        try:
            s_time = start[11:16] if len(start) >= 16 else start[:5]
            e_time = end[11:16] if len(end) >= 16 else end[:5]
            time_col = f"{s_time}-{e_time}"
        except Exception:
            time_col = ""
    time_col = time_col[:12].ljust(12)

    # Build date prefix (10 chars) for week/month views
    if show_date:
        date_col = _weekday_date(start)[:9].ljust(9) + " "
    else:
        date_col = ""

    prefix = date_col + time_col
    remaining = max(0, width - len(prefix))

    # Location suffix
    loc_suffix = ""
    if location:
        loc_suffix = f"  [{location[:20]}]"

    # Subject
    subj_max = max(0, remaining - len(loc_suffix))
    subj = subject[:subj_max]

    row = prefix + subj + loc_suffix
    return row[:width]


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class AgendaItemSelected(Message):
    """Fired when the highlighted item changes."""

    def __init__(self, event: dict[str, Any] | None) -> None:
        super().__init__()
        self.event = event


class AgendaItemDrilled(Message):
    """Fired when the user presses Enter / → / l to open detail."""

    def __init__(self, event: dict[str, Any] | None) -> None:
        super().__init__()
        self.event = event


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

PLACEHOLDER = "(no events)"


class AgendaList(Static):
    """Scrollable event list with vim-style keybindings.

    Emits :class:`AgendaItemSelected` on highlight change and
    :class:`AgendaItemDrilled` on Enter/→/l.
    """

    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("g", "move_top", "Top"),
        ("G", "move_bottom", "Bottom"),
        ("u", "page_up_half", "Half-page up"),
        ("l", "drill", "Open"),
        ("h", "back", "Back"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._data: list[dict[str, Any]] = []
        self._show_date: bool = False

    def compose(self) -> ComposeResult:
        lv = ListView(id="agenda-lv")
        yield lv

    def _lv(self) -> ListView:
        return self.query_one("#agenda-lv", ListView)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_rows(self, events: list[dict[str, Any]], *, show_date: bool = False) -> None:
        """Replace displayed rows with *events*."""
        self._data = list(events)
        self._show_date = show_date
        lv = self._lv()
        lv.clear()
        if not self._data:
            lv.append(ListItem(Static(PLACEHOLDER)))
            return
        width = self.size.width or 80
        for ev in self._data:
            row = render_row(ev, width, show_date=show_date)
            lv.append(ListItem(Static(row)))
        # Ensure first item is selected so current_item() works immediately
        lv.index = 0

    def current_item(self) -> dict[str, Any] | None:
        """Return the data dict for the selected row, or ``None``."""
        lv = self._lv()
        idx = lv.index
        if idx is None or idx >= len(self._data):
            return None
        return self._data[idx]

    @property
    def item_count(self) -> int:
        return len(self._data)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        event.stop()
        self.post_message(AgendaItemSelected(self.current_item()))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        self.post_message(AgendaItemDrilled(self.current_item()))

    def on_key(self, event: Any) -> None:
        key = event.key
        lv = self._lv()
        if key == "up":
            lv.action_cursor_up()
            event.stop()
        elif key == "down":
            lv.action_cursor_down()
            event.stop()
        elif key == "pageup":
            lv.action_scroll_up()
            event.stop()
        elif key in ("pagedown", "space"):
            lv.action_scroll_down()
            event.stop()
        elif key in ("enter", "right"):
            self.action_drill()
            event.stop()
        elif key == "left":
            self.action_back()
            event.stop()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_move_down(self) -> None:
        self._lv().action_cursor_down()

    def action_move_up(self) -> None:
        self._lv().action_cursor_up()

    def action_move_top(self) -> None:
        self._lv().index = 0

    def action_move_bottom(self) -> None:
        lv = self._lv()
        if self._data:
            lv.index = len(self._data) - 1

    def action_page_up_half(self) -> None:
        lv = self._lv()
        half = max(1, self.size.height // 2)
        lv.index = max(0, (lv.index or 0) - half)

    def action_page_down_half(self) -> None:
        lv = self._lv()
        half = max(1, self.size.height // 2)
        lv.index = min(max(0, len(self._data) - 1), (lv.index or 0) + half)

    def action_drill(self) -> None:
        self.post_message(AgendaItemDrilled(self.current_item()))

    def action_back(self) -> None:
        from textual.message import Message

        class _Back(Message):
            pass

        self.post_message(_Back())
