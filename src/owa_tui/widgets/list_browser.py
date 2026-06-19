"""ListBrowser: generic scrollable list widget with vim-style keybindings.

Wraps ``textual.widgets.ListView`` and provides:

* Keyboard navigation: j/k/↑/↓ move; g/G top/bottom; u/d half-page;
  PgUp/PgDn/Space page; Enter/→/l drill; h/← back.
* Messages: ``ItemSelected``, ``ItemDrilled``, ``BackPressed``.
* ``update_rows(items)`` — repopulates the list.
* ``current_item()`` — returns the selected data item or ``None``.
* ``render_item(item)`` — override in subclasses to customise row text.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import ListItem, ListView, Static

# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class ItemSelected(Message):
    """Fired when the cursor moves to a different item."""

    def __init__(self, item: Any) -> None:
        super().__init__()
        self.item = item


class ItemDrilled(Message):
    """Fired when the user presses Enter / → / l to open an item."""

    def __init__(self, item: Any) -> None:
        super().__init__()
        self.item = item


class BackPressed(Message):
    """Fired when the user presses h / ← to go back."""


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------


class ListBrowser(Widget):
    """Generic scrollable list with vim-style key bindings.

    Subclass and override :meth:`render_item` to customise the display
    string for each data item.  All keyboard handling is implemented here
    so tool-specific list widgets only need to supply the render logic.

    Parameters
    ----------
    items:
        Initial list of data items (can be empty; call ``update_rows`` later).
    *args / **kwargs:
        Forwarded to ``Widget.__init__``.
    """

    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("g", "move_top", "Top"),
        ("G", "move_bottom", "Bottom"),
        ("u", "page_up_half", "Half-page up"),
        ("d", "page_down_half", "Half-page down"),
        ("l", "drill", "Open"),
        ("h", "back", "Back"),
    ]

    _items: reactive[list[Any]] = reactive([], recompose=False)

    def __init__(self, items: list[Any] | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._data: list[Any] = list(items or [])

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        lv = ListView(*self._build_items(), id="list-view")
        yield lv

    def _build_items(self) -> list[ListItem]:
        return [ListItem(Static(self.render_item(item))) for item in self._data]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_item(self, item: Any) -> str:
        """Return the display string for *item*.  Override in subclasses."""
        return str(item)

    def update_rows(self, items: list[Any]) -> None:
        """Replace all rows with *items* and refresh the list."""
        self._data = list(items)
        lv = self.query_one("#list-view", ListView)
        lv.clear()
        for item in self._data:
            lv.append(ListItem(Static(self.render_item(item))))

    def current_item(self) -> Any | None:
        """Return the data item at the current cursor position, or ``None``."""
        lv = self.query_one("#list-view", ListView)
        idx = lv.index
        if idx is None or idx >= len(self._data):
            return None
        return self._data[idx]

    @property
    def item_count(self) -> int:
        """Number of items currently displayed."""
        return len(self._data)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Forward ListView selection as ItemDrilled."""
        event.stop()
        item = self.current_item()
        if item is not None:
            self.post_message(ItemDrilled(item))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Forward highlight change as ItemSelected."""
        event.stop()
        item = self.current_item()
        if item is not None:
            self.post_message(ItemSelected(item))

    # ------------------------------------------------------------------
    # Key actions
    # ------------------------------------------------------------------

    def _list_view(self) -> ListView:
        return self.query_one("#list-view", ListView)

    def action_move_down(self) -> None:
        self._list_view().action_cursor_down()

    def action_move_up(self) -> None:
        self._list_view().action_cursor_up()

    def action_move_top(self) -> None:
        lv = self._list_view()
        lv.index = 0

    def action_move_bottom(self) -> None:
        lv = self._list_view()
        if self._data:
            lv.index = len(self._data) - 1

    def action_page_up_half(self) -> None:
        lv = self._list_view()
        half = max(1, self.size.height // 2)
        lv.index = max(0, (lv.index or 0) - half)

    def action_page_down_half(self) -> None:
        lv = self._list_view()
        half = max(1, self.size.height // 2)
        lv.index = min(len(self._data) - 1, (lv.index or 0) + half)

    def action_drill(self) -> None:
        item = self.current_item()
        if item is not None:
            self.post_message(ItemDrilled(item))

    def action_back(self) -> None:
        self.post_message(BackPressed())

    # Standard arrow-key and PgUp/PgDn/Space pass-through to ListView
    def on_key(self, event: Any) -> None:
        key = event.key
        lv = self._list_view()
        if key in ("up",):
            lv.action_cursor_up()
            event.stop()
        elif key in ("down",):
            lv.action_cursor_down()
            event.stop()
        elif key in ("pageup",):
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
