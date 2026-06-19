"""screen.py — OwaListScreen: generic flat-list+detail+search+menu base.

Factored from the proven triply-repeated pattern in:
  - owa_tui.screens.mail.MailScreen
  - owa_tui.screens.cal.screen.CalScreen
  - owa_tui.screens.people.PeopleScreen

Contract
--------
Subclass ``OwaListScreen`` and implement the four abstract hooks:

    async def fetch_items(self, search: str) -> list[dict]:
        \"\"\"Return the data rows for the list.  Called in a worker thread.
        Raise on hard failure; return [] for empty results.  Do not touch
        Textual state — the base class marshals results back to the main
        thread.\"\"\"

    def render_row(self, item: dict, width: int) -> str:
        \"\"\"Return the display string for one list row.\"\"\"

    def render_detail(self, item: dict) -> str:
        \"\"\"Return the full detail text for the detail pane / full-screen view.\"\"\"

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        \"\"\"Return (overlay_title, settings_fields) for the Esc menu.
        settings_fields is [(field_name, display_label), ...].\"\"\"

All other behaviour (layout, search modal, Esc overlay, keybindings,
status bar, detail-pane split, full-screen fallback) is handled here and
should not be re-implemented in concrete subclasses.

Optional overridable hooks
--------------------------
- ``on_item_activated(item)``  — called when Enter/l is pressed (default:
  shows detail).
- ``on_search_query(query)``   — default is to call fetch_items(query).
- ``handle_menu_result(result)`` — called with the overlay action string;
  the base handles 'resume', 'quit', 'help'.  Override to handle
  tool-specific 'cycle:*' values.  Call super() first.
- ``open_browser_for(item)``   — default is a no-op (returns None).  Return
  a URL string to trigger ``webbrowser.open``.
- ``help_text()``              — status-bar text shown for 'help'.
- ``sort_items(items)``        — optional client-side sort before display.
  Default: identity (returns items unchanged).
- ``initial_items``            — pass a list to __init__ to pre-load rows
  (bypasses fetch; useful for tests).

Constructor parameters
----------------------
config : dict
    owa-tools config dict (forwarded to auth helper).
tool_name : str
    Name used when minting auth tokens (e.g. 'owa-mail').
audience : str
    Auth audience ('outlook' or 'graph').
title : str
    Screen TITLE override (defaults to tool_name).
detail_pane_mode : str
    One of 'right', 'bottom', 'off'.  Default 'right'.
split_ratio : int
    Percentage (0-100) of the screen width/height given to the list.
    Default 50.
debug : bool
    Enable verbose adapter logging.
initial_items : list[dict] | None
    Pre-populated items (skip fetch; for tests).
"""

from __future__ import annotations

import webbrowser
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from owa_tui.screens.base.keys import LIST_BINDINGS
from owa_tui.widgets.status_bar import StatusBar

# ---------------------------------------------------------------------------
# Internal search modal (shared, not exported)
# ---------------------------------------------------------------------------


class _SearchModal(ModalScreen[str | None]):
    """Generic search prompt modal used by OwaListScreen."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    _SearchModal {
        align: center middle;
    }
    _SearchModal #search-box {
        width: 60;
        height: auto;
        border: solid $border;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, prompt: str = "Search:", placeholder: str = "search term…") -> None:
        super().__init__()
        self._prompt = prompt
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Static(id="search-box"):
            yield Label(self._prompt, classes="overlay-title")
            yield Input(placeholder=self._placeholder, id="search-input")
            yield Label("Enter to search  Esc to cancel", classes="overlay-hint")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Internal full-screen detail view
# ---------------------------------------------------------------------------


class _FullDetailScreen(Screen[None]):
    """Pushed when detail_pane_mode == 'off' and user opens an item."""

    BINDINGS = [
        Binding("q", "pop_screen", "Back"),
        Binding("escape", "pop_screen", "Back"),
        Binding("h", "pop_screen", "Back"),
        Binding("left", "pop_screen", "Back"),
        Binding("j", "scroll_down_line", "Down", show=False),
        Binding("k", "scroll_up_line", "Up", show=False),
        Binding("space", "scroll_down_page", "Page Down", show=False),
        Binding("pagedown", "scroll_down_page", "Page Down", show=False),
        Binding("pageup", "scroll_up_page", "Page Up", show=False),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
    ]

    def __init__(self, content: str, title: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._content = content
        self._title = title

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(id="full-detail-scroll"):
            yield Static(self._content, id="full-detail-content")
        yield Footer()

    def on_mount(self) -> None:
        if self._title:
            self.title = self._title

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

    def _scroll(self) -> ScrollableContainer:
        return self.query_one("#full-detail-scroll", ScrollableContainer)

    def action_scroll_down_line(self) -> None:
        self._scroll().scroll_down(animate=False)

    def action_scroll_up_line(self) -> None:
        self._scroll().scroll_up(animate=False)

    def action_scroll_down_page(self) -> None:
        self._scroll().scroll_page_down(animate=False)

    def action_scroll_up_page(self) -> None:
        self._scroll().scroll_page_up(animate=False)

    def action_scroll_top(self) -> None:
        self._scroll().scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        self._scroll().scroll_end(animate=False)


# ---------------------------------------------------------------------------
# Internal list widget
# ---------------------------------------------------------------------------


class _OwaList(ListView):
    """Thin ListView subclass that calls a render callback for each row.

    Uses a caller-supplied ``render_fn(item, width) -> str`` so the base
    screen owns the rendering logic without needing a custom ListView subclass
    per tool.
    """

    def __init__(
        self,
        items: list[dict],
        render_fn: Any,
        empty_label: str = "(no items)",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._items: list[dict] = list(items)
        self._render_fn = render_fn
        self._empty_label = empty_label

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_rows(self, items: list[dict]) -> None:
        self._items = list(items)
        self._rebuild()

    def current_item(self) -> dict | None:
        idx = self.index
        if idx is None or idx >= len(self._items):
            return None
        return self._items[idx]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        self.clear()
        if not self._items:
            self.append(ListItem(Static(self._empty_label, id="owa-list-empty")))
            return
        w = self.size.width or 80
        for item in self._items:
            text = self._render_fn(item, w)
            self.append(ListItem(Label(text)))

    def on_mount(self) -> None:
        self._rebuild()

    # NB: do NOT handle/stop ListView.Highlighted / .Selected here — they must
    # bubble to OwaListScreen, which drives the detail-pane preview and item
    # activation. Swallowing them silently breaks cursor-move auto-preview.


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------


class _LayoutRight(Horizontal):
    def __init__(self, ratio: int, list_widget: _OwaList, detail: ScrollableContainer) -> None:
        super().__init__(id="owa-list-layout")
        self._ratio = ratio
        self._lw = list_widget
        self._dw = detail

    def compose(self) -> ComposeResult:
        self._lw.styles.width = f"{self._ratio}%"
        self._dw.styles.width = f"{100 - self._ratio}%"
        yield self._lw
        yield self._dw


class _LayoutBottom(Vertical):
    def __init__(self, ratio: int, list_widget: _OwaList, detail: ScrollableContainer) -> None:
        super().__init__(id="owa-list-layout")
        self._ratio = ratio
        self._lw = list_widget
        self._dw = detail

    def compose(self) -> ComposeResult:
        self._lw.styles.height = f"{self._ratio}%"
        self._dw.styles.height = f"{100 - self._ratio}%"
        yield self._lw
        yield self._dw


class _LayoutOff(Horizontal):
    def __init__(self, list_widget: _OwaList) -> None:
        super().__init__(id="owa-list-layout")
        self._lw = list_widget

    def compose(self) -> ComposeResult:
        yield self._lw


# ---------------------------------------------------------------------------
# Detail pane (generic — content set via update_content)
# ---------------------------------------------------------------------------


class _DetailPane(ScrollableContainer):
    DEFAULT_CSS = """
    _DetailPane {
        overflow-y: scroll;
        padding: 0 1;
        border-left: solid $border;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="owa-detail-content")

    def update_content(self, text: str) -> None:
        self.query_one("#owa-detail-content", Static).update(text)

    def clear(self) -> None:
        self.update_content("")


# ---------------------------------------------------------------------------
# OwaListScreen
# ---------------------------------------------------------------------------


class OwaListScreen(Screen[None]):
    """Generic flat-list + detail-pane + search + Esc-menu base screen.

    Subclass this and implement:
        async fetch_items(search: str) -> list[dict]
        render_row(item: dict, width: int) -> str
        render_detail(item: dict) -> str
        menu_config() -> tuple[str, list[tuple[str, str]]]

    See module docstring for the full API.
    """

    BINDINGS: list[Binding] = list(LIST_BINDINGS)  # type: ignore[assignment]

    # Reactive state ----------------------------------------------------------
    _items: reactive[list[dict]] = reactive(list, recompose=False)
    _selected_idx: reactive[int] = reactive(0)
    _search: reactive[str] = reactive("")
    _status: reactive[str] = reactive("")
    _mode: reactive[str] = reactive("list")  # 'list' | 'detail'

    # -------------------------------------------------------------------------
    # Constructor
    # -------------------------------------------------------------------------

    def __init__(
        self,
        *,
        config: dict[str, Any] | None = None,
        tool_name: str = "owa-tool",
        audience: str = "graph",
        title: str = "",
        detail_pane_mode: str = "right",
        split_ratio: int = 50,
        debug: bool = False,
        initial_items: list[dict] | None = None,
        search_prompt: str = "Search:",
        search_placeholder: str = "search term…",
        empty_label: str = "(no items)",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = config or {}
        self._tool_name = tool_name
        self._audience = audience
        self._screen_title = title or tool_name
        self._detail_pane_mode = detail_pane_mode
        self._split_ratio = split_ratio
        self._debug = debug
        self._search_prompt = search_prompt
        self._search_placeholder = search_placeholder
        self._empty_label = empty_label
        self._selected_item: dict | None = None

        # Pre-loaded items bypass the fetch worker (used in tests / offline mode)
        if initial_items is not None:
            self._items = list(initial_items)
            self._preloaded = True
        else:
            self._preloaded = False

    # -------------------------------------------------------------------------
    # Abstract hooks — subclass MUST implement
    # -------------------------------------------------------------------------

    async def fetch_items(self, search: str = "") -> list[dict]:  # noqa: B006
        """Fetch data rows.  Runs inside a @work thread — do not touch UI state.

        Raise on unrecoverable error; return [] for empty results.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement fetch_items()")

    def render_row(self, item: dict, width: int) -> str:
        """Return the display string for one list row."""
        raise NotImplementedError(f"{type(self).__name__} must implement render_row()")

    def render_detail(self, item: dict) -> str:
        """Return the full detail text for the detail pane / full-screen view."""
        raise NotImplementedError(f"{type(self).__name__} must implement render_detail()")

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        """Return (overlay_title, settings_fields) for the Esc overlay.

        settings_fields: [(field_name, display_label), ...]
        An empty settings_fields list means no Settings sub-menu.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement menu_config()")

    # -------------------------------------------------------------------------
    # Optional overridable hooks
    # -------------------------------------------------------------------------

    def on_item_activated(self, item: dict) -> None:
        """Called when the user presses Enter/l on an item (after detail is shown).

        Default: shows the detail pane.  Override to add extra behaviour
        (e.g. mail opens the body fetch worker).  Call super() to keep the
        default detail display.
        """
        self._show_detail(item)

    def on_search_query(self, query: str) -> None:
        """Called with the query string after the search modal is dismissed.

        Default: triggers fetch_items(query) via the worker.
        """
        self._search = query
        self._load_items(query)

    def handle_menu_result(self, result: str) -> None:
        """Called with the overlay action string.

        The base handles 'resume', 'quit', 'help'.  Override to handle
        tool-specific 'cycle:*' values.  Call super() first.

        Example::

            def handle_menu_result(self, result: str) -> None:
                super().handle_menu_result(result)
                if result.startswith("cycle:"):
                    field = result[len("cycle:"):]
                    self.my_settings = self.my_settings.cycle(field)
                    self._refresh_list()
        """
        if result in (None, "resume"):
            return
        if result == "quit":
            self.app.exit()
        elif result == "help":
            self._status = self.help_text()

    def open_browser_for(self, item: dict) -> str | None:
        """Return a URL to open in the browser for *item*, or None.

        Default: returns None (browser action is a no-op).
        """
        return None

    def help_text(self) -> str:
        """Status-bar text shown when the user selects Help from the menu."""
        return (
            "j/k move  g/G top/bottom  Enter open  / search  r refresh  o browser  q quit"
        )

    def sort_items(self, items: list[dict]) -> list[dict]:
        """Client-side sort applied before populating the list.  Default: identity."""
        return items

    # -------------------------------------------------------------------------
    # Composition
    # -------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield self._build_layout()
        yield StatusBar(self._status, id="owa-status-bar")
        yield Footer()

    def _build_layout(self) -> Any:
        list_widget = _OwaList(
            self.sort_items(self._items),
            self.render_row,
            empty_label=self._empty_label,
            id="owa-item-list",
        )
        detail = _DetailPane(id="owa-detail-pane")
        mode = self._detail_pane_mode
        ratio = self._split_ratio
        if mode == "right":
            return _LayoutRight(ratio, list_widget, detail)
        if mode == "bottom":
            return _LayoutBottom(ratio, list_widget, detail)
        return _LayoutOff(list_widget)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def on_mount(self) -> None:
        self.title = self._screen_title
        if not self._preloaded:
            self._load_items()

    # -------------------------------------------------------------------------
    # Worker
    # -------------------------------------------------------------------------

    @work(thread=True)
    def _load_items(self, search: str = "") -> None:
        """Background thread: call fetch_items() and marshal results to main thread."""
        import asyncio  # noqa: PLC0415

        self.app.call_from_thread(lambda: setattr(self, "_status", "Loading…"))
        try:
            items = asyncio.run(self.fetch_items(search))
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(lambda: setattr(self, "_status", f"error: {err}"))
            return
        self.app.call_from_thread(self._apply_items, items, search)

    def _apply_items(self, items: list[dict], search: str) -> None:
        """Main-thread callback: update reactive state and rebuild the list."""
        self._items = items
        self._search = search
        self._selected_idx = 0
        self._selected_item = None
        self._refresh_list()
        count = len(items)
        noun = "item" if count == 1 else "items"
        self._status = f"{count} {noun}"

    # -------------------------------------------------------------------------
    # Reactive watchers
    # -------------------------------------------------------------------------

    def watch__status(self, value: str) -> None:
        try:
            self.query_one("#owa-status-bar", StatusBar).update(value)
        except Exception:
            pass

    def watch__selected_idx(self, value: int) -> None:
        lw = self._list_widget()
        if lw is not None and lw.index != value:
            lw.index = value

    # -------------------------------------------------------------------------
    # Actions (implement the LIST_BINDINGS action names)
    # -------------------------------------------------------------------------

    def action_move_down(self) -> None:
        lw = self._list_widget()
        if lw is not None:
            lw.action_cursor_down()

    def action_move_up(self) -> None:
        lw = self._list_widget()
        if lw is not None:
            lw.action_cursor_up()

    def action_page_down(self) -> None:
        lw = self._list_widget()
        if lw is not None:
            half = max(1, (lw.size.height or 10) // 2)
            for _ in range(half):
                lw.action_cursor_down()

    def action_page_up(self) -> None:
        lw = self._list_widget()
        if lw is not None:
            half = max(1, (lw.size.height or 10) // 2)
            for _ in range(half):
                lw.action_cursor_up()

    def action_go_top(self) -> None:
        lw = self._list_widget()
        if lw is not None:
            lw.index = 0
            self._selected_idx = 0

    def action_go_bottom(self) -> None:
        lw = self._list_widget()
        sorted_items = self.sort_items(self._items)
        if lw is not None and sorted_items:
            last = len(sorted_items) - 1
            lw.index = last
            self._selected_idx = last

    def action_open_item(self) -> None:
        item = self._current_item()
        if item is not None:
            self.on_item_activated(item)

    def action_close_detail(self) -> None:
        if self._detail_pane_mode == "off":
            return
        lw = self._list_widget()
        if lw is not None:
            lw.focus()
        self._mode = "list"

    def action_focus_pane(self) -> None:
        if self._detail_pane_mode == "off":
            return
        try:
            pane = self.query_one("#owa-detail-pane", _DetailPane)
            if self.focused == pane:
                lw = self._list_widget()
                if lw:
                    lw.focus()
            else:
                pane.focus()
        except Exception:
            pass

    def action_refresh(self) -> None:
        self._load_items(search=self._search)

    def action_search(self) -> None:
        modal = _SearchModal(
            prompt=self._search_prompt,
            placeholder=self._search_placeholder,
        )

        def _on_result(query: str | None) -> None:
            if query:
                self.on_search_query(query)

        self.app.push_screen(modal, _on_result)

    def action_open_browser(self) -> None:
        item = self._current_item()
        if item is None:
            self._status = "no item selected"
            return
        url = self.open_browser_for(item)
        if not url:
            self._status = "no browser link for this item"
            return
        try:
            webbrowser.open(url)
            self._status = f"opened: {url[:60]}"
        except Exception as exc:
            self._status = f"could not open browser: {exc}"

    def action_open_menu(self) -> None:
        from owa_tui.widgets.settings_overlay import SettingsOverlay  # noqa: PLC0415

        overlay_title, settings_fields = self.menu_config()
        overlay = SettingsOverlay(
            title_lines=[overlay_title],
            top_items=[
                ("Resume", "resume"),
                ("Settings", "settings"),
                ("Help", "help"),
                ("Quit", "quit"),
            ],
            settings_fields=settings_fields,
            settings=None,
        )
        self.app.push_screen(overlay, self.handle_menu_result)

    def action_quit(self) -> None:
        self.app.pop_screen()

    # -------------------------------------------------------------------------
    # ListView event bridge
    # -------------------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Sync _selected_idx when the ListView cursor moves."""
        event.stop()
        lw = self._list_widget()
        if lw is None:
            return
        item = lw.current_item()
        if item is not None:
            self._selected_item = item
            sorted_items = self.sort_items(self._items)
            try:
                self._selected_idx = sorted_items.index(item)
            except ValueError:
                self._selected_idx = 0
            # Auto-preview in the split pane on cursor move
            if self._detail_pane_mode != "off":
                self._update_detail_pane(item)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Treat ListView 'selected' (Enter) as open_item."""
        event.stop()
        lw = self._list_widget()
        if lw is None:
            return
        item = lw.current_item()
        if item is not None:
            self.on_item_activated(item)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _list_widget(self) -> _OwaList | None:
        try:
            return self.query_one("#owa-item-list", _OwaList)
        except Exception:
            return None

    def _detail_pane(self) -> _DetailPane | None:
        try:
            return self.query_one("#owa-detail-pane", _DetailPane)
        except Exception:
            return None

    def _current_item(self) -> dict | None:
        lw = self._list_widget()
        if lw is not None:
            return lw.current_item()
        return self._selected_item

    def _show_detail(self, item: dict) -> None:
        """Display item detail — either in the split pane or as a full-screen push."""
        text = self.render_detail(item)
        if self._detail_pane_mode == "off":
            self.app.push_screen(_FullDetailScreen(text, title=self._screen_title))
        else:
            self._update_detail_pane(item)
            self._mode = "detail"

    def _update_detail_pane(self, item: dict) -> None:
        pane = self._detail_pane()
        if pane is None:
            return
        try:
            text = self.render_detail(item)
            pane.update_content(text)
        except Exception:
            pass

    def _refresh_list(self) -> None:
        lw = self._list_widget()
        if lw is None:
            return
        lw.update_rows(self.sort_items(self._items))
