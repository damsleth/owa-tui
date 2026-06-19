"""MailScreen — Textual screen for owa-mail (Microsoft 365 mail TUI).

Architecture
------------
MailScreen(Screen)
  ├── Header
  ├── Horizontal / Vertical  (depends on settings.reading_pane)
  │   ├── MessageList(ListView)   — left/top pane
  │   └── ReaderPane(ScrollableContainer) — right/bottom (hidden when 'off')
  └── StatusBar

Reading-pane modes
------------------
right  — Horizontal split: list left (split_ratio %), pane right
bottom — Vertical split: list top (split_ratio %), pane bottom
off    — list fills screen; Enter/l pushes full-screen ReaderScreen

All blocking owa-tools I/O runs in @work(thread=True) workers — the
Textual event loop is never stalled.
"""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

from owa_tui.mail.list_row import list_row
from owa_tui.mail.settings import (
    DEFAULTS as SETTINGS_DEFAULTS,
)
from owa_tui.mail.settings import (
    MailSettings,
    cycle,
    from_config,
    to_config_dict,
)
from owa_tui.mail.sort import sort_messages
from owa_tui.widgets.settings_overlay import SettingsOverlay
from owa_tui.widgets.status_bar import StatusBar

PAGE_SIZE = 50
SHOW_SELECT = (
    "Id,ConversationId,ReceivedDateTime,SentDateTime,Subject,From,"
    "ToRecipients,CcRecipients,BccRecipients,Body,BodyPreview,IsRead,"
    "HasAttachments,Importance,Flag,WebLink,ParentFolderId,"
    "InternetMessageHeaders"
)

# ---------------------------------------------------------------------------
# Pure-Python helpers
# ---------------------------------------------------------------------------


def _render_message_body(msg: dict) -> str:
    """Render a full message for the reader pane (plain text, HTML stripped)."""
    try:
        from owa_mail.format import format_message_pretty  # type: ignore[import]

        return format_message_pretty(msg)
    except Exception:
        pass
    # Fallback: plain-text render without owa_mail.format
    import html
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self._parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self._parts.append(data)

        def get_text(self) -> str:
            return "".join(self._parts)

    lines: list[str] = []
    for label, key in (
        ("From", "from"),
        ("To", "to"),
        ("Date", "received"),
        ("Subject", "subject"),
    ):
        val = msg.get(key) or ""
        if val:
            lines.append(f"{label}: {val}")
    lines.append("")
    body = msg.get("body") or msg.get("preview") or ""
    if (msg.get("body_type") or "").lower() == "html":
        s = _Stripper()
        s.feed(html.unescape(body))
        body = s.get_text()
    lines.append(body)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class ReaderPane(ScrollableContainer):
    """Scrollable reading pane for a single message."""

    DEFAULT_CSS = """
    ReaderPane {
        overflow-y: scroll;
        padding: 0 1;
        border-left: solid $border;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="reader-content")

    def show_message(self, msg: dict) -> None:
        content = _render_message_body(msg)
        self.query_one("#reader-content", Static).update(content)

    def clear(self) -> None:
        self.query_one("#reader-content", Static).update("")


class MessageList(ListView):
    """Scrollable message list widget with vim-style keybindings.

    Posts ``MessageList.ItemSelected`` when the highlighted row changes
    and ``MessageList.ItemActivated`` when the user opens a message.
    """

    @dataclass
    class ItemSelected(Message):
        msg: dict

    @dataclass
    class ItemActivated(Message):
        msg: dict

    def __init__(self, messages: list[dict], settings: MailSettings, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._messages: list[dict] = list(messages)
        self._settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_messages(self, messages: list[dict], settings: MailSettings) -> None:
        self._messages = list(messages)
        self._settings = settings
        self._rebuild()

    def current_msg(self) -> dict | None:
        idx = self.index
        if idx is None or idx >= len(self._messages):
            return None
        return self._messages[idx]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        self.clear()
        if not self._messages:
            self.append(ListItem(Static("(no messages)", id="no-messages-label")))
            return
        for msg in self._messages:
            row_text = list_row(
                msg,
                width=self.size.width or 80,
                date_fmt=self._settings.date_format,
                custom_fmt=self._settings.date_custom,
            )
            style = "bold" if not msg.get("is_read") else ""
            label = Label(f"[{style}]{row_text}[/{style}]" if style else row_text)
            self.append(ListItem(label))

    # ------------------------------------------------------------------
    # Textual overrides
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._rebuild()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        event.stop()
        msg = self.current_msg()
        if msg is not None:
            self.post_message(self.ItemSelected(msg))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        msg = self.current_msg()
        if msg is not None:
            self.post_message(self.ItemActivated(msg))


# ---------------------------------------------------------------------------
# Search modal
# ---------------------------------------------------------------------------


class SearchModal(ModalScreen[str | None]):
    """Simple search prompt modal."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    SearchModal {
        align: center middle;
    }
    SearchModal #search-box {
        width: 60;
        height: auto;
        border: solid $border;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="search-box"):
            yield Label("Search (KQL):", classes="overlay-title")
            yield Input(placeholder="search term…", id="search-input")
            yield Label("Enter to search  Esc to cancel", classes="overlay-hint")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Full-screen reader screen (used when reading_pane == 'off')
# ---------------------------------------------------------------------------


class ReaderScreen(Screen[None]):
    """Full-screen reader pushed when reading_pane is 'off'."""

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

    def __init__(self, msg: dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._msg = msg

    def compose(self) -> ComposeResult:
        yield Header()
        yield ReaderPane(id="full-reader-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(ReaderPane).show_message(self._msg)

    def action_pop_screen(self) -> None:
        self.app.pop_screen()

    def action_scroll_down_line(self) -> None:
        self.query_one(ReaderPane).scroll_down(animate=False)

    def action_scroll_up_line(self) -> None:
        self.query_one(ReaderPane).scroll_up(animate=False)

    def action_scroll_down_page(self) -> None:
        self.query_one(ReaderPane).scroll_page_down(animate=False)

    def action_scroll_up_page(self) -> None:
        self.query_one(ReaderPane).scroll_page_up(animate=False)

    def action_scroll_top(self) -> None:
        self.query_one(ReaderPane).scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        self.query_one(ReaderPane).scroll_end(animate=False)


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------


class MailScreen(Screen[None]):
    """Textual screen for owa-mail: message list + reading pane."""

    TITLE = "owa-mail"

    BINDINGS = [
        Binding("j", "move_down", "Down", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("d", "page_down", "Page Down", show=False),
        Binding("u", "page_up", "Page Up", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),
        Binding("enter", "open_message", "Open"),
        Binding("l", "open_message", "Open", show=False),
        Binding("h", "close_reader", "Back", show=False),
        Binding("left", "close_reader", "Back", show=False),
        Binding("tab", "focus_pane", "Focus pane", show=False),
        Binding("r", "toggle_read", "Toggle read"),
        Binding("o", "open_browser", "Browser"),
        Binding("/", "search", "Search"),
        Binding("escape", "open_menu", "Menu"),
        Binding("q", "quit", "Quit"),
    ]

    # Reactive state
    messages: reactive[list[dict]] = reactive(list, recompose=False)
    selected: reactive[int] = reactive(0)
    folder: reactive[str] = reactive("Inbox")
    search: reactive[str] = reactive("")
    settings: reactive[MailSettings] = reactive(lambda: MailSettings())
    status: reactive[str] = reactive("")
    mode: reactive[str] = reactive("list")

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        debug: bool = False,
        # Allow pre-loading messages for tests (no live auth needed)
        initial_messages: list[dict] | None = None,
        initial_settings: MailSettings | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = config or {}
        self._debug = debug
        self._body_cache: dict[str, dict] = {}
        self._api_base: str = self._config.get("api_base", "https://outlook.office.com/api/v2.0")
        self._selected_msg: dict | None = None

        # Load settings from config (or use provided initial_settings for tests)
        if initial_settings is not None:
            self.settings = initial_settings
        else:
            try:
                from owa_mail.config import load_config  # type: ignore[import]

                self.settings = from_config(load_config())
            except Exception:
                self.settings = SETTINGS_DEFAULTS

        # Pre-load messages for tests without live auth
        if initial_messages is not None:
            self.messages = list(initial_messages)
            self._messages_preloaded = True
        else:
            self._messages_preloaded = False

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield self._build_layout()
        yield StatusBar(self.status, id="status-bar")
        yield Footer()

    def _build_layout(self) -> Any:
        """Build the list + pane container based on reading_pane setting."""
        pane = self.settings.reading_pane
        ratio = self.settings.split_ratio

        msg_list = MessageList(
            self._sorted_messages(),
            self.settings,
            id="message-list",
        )

        if pane == "right":
            container = Horizontal(id="mail-layout")
            msg_list.styles.width = f"{ratio}%"
            reader = ReaderPane(id="reader-pane")
            reader.styles.width = f"{100 - ratio}%"
            # Horizontal children assigned in compose order
            container._nodes_to_add = [msg_list, reader]  # type: ignore[attr-defined]
            # Use actual compose approach
            return _LayoutRight(ratio, msg_list, reader)
        elif pane == "bottom":
            return _LayoutBottom(ratio, msg_list, ReaderPane(id="reader-pane"))
        else:  # off
            return _LayoutOff(msg_list)

    # ------------------------------------------------------------------
    # Mount / lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        if not self._messages_preloaded:
            self._fetch_list()

    def _sorted_messages(self) -> list[dict]:
        return sort_messages(self.messages, self.settings.sort_by)

    # ------------------------------------------------------------------
    # Workers (blocking I/O off event loop)
    # ------------------------------------------------------------------

    @work(thread=True)
    def _fetch_list(
        self,
        search: str = "",
        since: str = "",
        until: str = "",
    ) -> None:
        """Fetch message list from Graph API in a background thread."""
        self.app.call_from_thread(lambda: setattr(self, "status", "Loading messages…"))
        try:
            from owa_mail.api import api_get  # type: ignore[import]
            from owa_mail.messages import (  # type: ignore[import]
                build_list_query,
                normalize_messages,
            )

            token = self._get_token_sync()
            if not token:
                self.app.call_from_thread(lambda: setattr(self, "status", "auth failed"))
                return

            params = build_list_query(
                search=search,
                since=since,
                until=until,
                limit=PAGE_SIZE,
            )
            path = _build_messages_path(params)
            raw = api_get(self._api_base, path, token, debug=self._debug)
            if raw is None:
                if search:
                    self.app.call_from_thread(self._on_search_failed)
                else:
                    self.app.call_from_thread(
                        lambda: setattr(self, "status", "fetch failed: no data returned")
                    )
                return

            msgs = normalize_messages(raw, keep_body=False)
            self.app.call_from_thread(self._apply_messages, msgs, search)
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(lambda: setattr(self, "status", f"error: {err}"))

    def _get_token_sync(self) -> str:
        """Mint a fresh auth token via owa-piggy (runs in worker thread)."""
        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        return access_token_for(self._config, tool_name="owa-mail", audience="outlook")

    def _apply_messages(self, msgs: list[dict], search: str) -> None:
        """Called on main thread after successful list fetch."""
        self.messages = msgs
        self.search = search
        self.selected = 0
        self._body_cache = {}
        self._refresh_list()
        count = len(msgs)
        self.status = f"{count} message{'s' if count != 1 else ''}"

    def _on_search_failed(self) -> None:
        self.status = "search failed"

    @work(thread=True)
    def _fetch_body(self, msg_id: str) -> None:
        """Lazy-fetch a message body in a background thread."""
        if msg_id in self._body_cache:
            self.app.call_from_thread(self._show_cached_body, msg_id)
            return
        try:
            from owa_mail.api import api_get  # type: ignore[import]
            from owa_mail.messages import normalize_message  # type: ignore[import]

            token = self._get_token_sync()
            if not token:
                self.app.call_from_thread(self._on_body_failed)
                return

            path = f"me/messages/{msg_id}?$select={SHOW_SELECT}"
            raw = api_get(self._api_base, path, token, debug=self._debug)
            if raw is None:
                self.app.call_from_thread(self._on_body_failed)
                return

            full_msg = normalize_message(raw)
            self._body_cache[msg_id] = full_msg
            self.app.call_from_thread(self._show_cached_body, msg_id)
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(
                lambda: setattr(self, "status", f"failed to load message: {err}")
            )
            self.app.call_from_thread(lambda: setattr(self, "mode", "list"))

    def _show_cached_body(self, msg_id: str) -> None:
        """Display cached body in reading pane or push ReaderScreen."""
        full_msg = self._body_cache.get(msg_id)
        if full_msg is None:
            self._on_body_failed()
            return

        if self.settings.reading_pane == "off":
            self.app.push_screen(ReaderScreen(full_msg))
        else:
            try:
                pane = self.query_one("#reader-pane", ReaderPane)
                pane.show_message(full_msg)
                self.mode = "reader"
            except Exception:
                self.app.push_screen(ReaderScreen(full_msg))

    def _on_body_failed(self) -> None:
        self.status = "failed to load message"
        self.mode = "list"

    @work(thread=True)
    def _patch_read(self, msg_id: str, new_read: bool) -> None:
        """PATCH IsRead on the Graph API in a background thread."""
        try:
            from owa_mail.api import api_request  # type: ignore[import]

            token = self._get_token_sync()
            if not token:
                return
            api_request(
                "PATCH",
                self._api_base,
                f"me/messages/{msg_id}",
                token,
                body={"IsRead": new_read},
                debug=self._debug,
            )
        except Exception:
            pass  # optimistic update already applied locally

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_move_down(self) -> None:
        ml = self._message_list()
        if ml is not None:
            ml.action_cursor_down()

    def action_move_up(self) -> None:
        ml = self._message_list()
        if ml is not None:
            ml.action_cursor_up()

    def action_page_down(self) -> None:
        ml = self._message_list()
        if ml is not None:
            half = max(1, (ml.size.height or 10) // 2)
            for _ in range(half):
                ml.action_cursor_down()

    def action_page_up(self) -> None:
        ml = self._message_list()
        if ml is not None:
            half = max(1, (ml.size.height or 10) // 2)
            for _ in range(half):
                ml.action_cursor_up()

    def action_go_top(self) -> None:
        ml = self._message_list()
        if ml is not None:
            ml.index = 0
            self.selected = 0

    def action_go_bottom(self) -> None:
        ml = self._message_list()
        sorted_msgs = self._sorted_messages()
        if ml is not None and sorted_msgs:
            last = len(sorted_msgs) - 1
            ml.index = last
            self.selected = last

    def action_open_message(self) -> None:
        msg = self._current_msg()
        if msg is None:
            return
        msg_id = msg.get("id") or ""
        if not msg_id:
            return
        if msg_id in self._body_cache:
            self._show_cached_body(msg_id)
        else:
            self._fetch_body(msg_id)

    def action_close_reader(self) -> None:
        if self.settings.reading_pane == "off":
            # Nothing to close from list view — pop if we're inside a ReaderScreen
            pass
        else:
            try:
                ml = self._message_list()
                if ml:
                    ml.focus()
            except Exception:
                pass
            self.mode = "list"

    def action_focus_pane(self) -> None:
        if self.settings.reading_pane == "off":
            return
        try:
            pane = self.query_one("#reader-pane", ReaderPane)
            if self.focused == pane:
                ml = self._message_list()
                if ml:
                    ml.focus()
            else:
                pane.focus()
        except Exception:
            pass

    def action_toggle_read(self) -> None:
        msg = self._current_msg()
        if msg is None:
            return
        old_read = msg.get("is_read", False)
        new_read = not old_read
        # Optimistic local update
        msg["is_read"] = new_read
        self._refresh_list()
        self.status = f"Marked as {'read' if new_read else 'unread'}"
        msg_id = msg.get("id") or ""
        if msg_id:
            self._patch_read(msg_id, new_read)

    def action_open_browser(self) -> None:
        msg = self._current_msg()
        if msg is None:
            return
        url = msg.get("web_link") or ""
        if not url:
            self.status = "no web link"
            return
        webbrowser.open(url)
        self.status = f"Opened in browser: {url[:60]}"

    def action_search(self) -> None:
        def _on_search_result(query: str | None) -> None:
            if not query:
                return
            self._fetch_list(search=query)

        self.app.push_screen(SearchModal(), _on_search_result)

    def action_open_menu(self) -> None:
        settings_fields = [
            ("reading_pane", f"Reading pane: {self.settings.reading_pane}"),
            ("split_ratio", f"Split ratio: {self.settings.split_ratio}"),
            ("sort_by", f"Sort by: {self.settings.sort_by}"),
            ("date_format", f"Date format: {self.settings.date_format}"),
        ]
        overlay = SettingsOverlay(
            title_lines=["owa-mail — settings"],
            top_items=[
                ("Resume", "resume"),
                ("Settings", "settings"),
                ("Help", "help"),
                ("Quit", "quit"),
            ],
            settings_fields=settings_fields,
            settings=None,  # We handle cycle ourselves
        )
        self.app.push_screen(overlay, self._handle_overlay)

    def _handle_overlay(self, result: str) -> None:
        if result == "resume" or result is None:
            return
        if result == "quit":
            self.app.exit()
            return
        if result == "help":
            self.status = "j/k move  g/G top/bottom  Enter open  / search  r toggle-read  o browser"
            return
        if result.startswith("cycle:"):
            field = result[len("cycle:"):]
            if field == "reading_pane":
                new_settings = cycle(self.settings, "reading_pane")
                self._apply_settings(new_settings)
            elif field == "split_ratio":
                new_settings = cycle(self.settings, "split_ratio")
                self._apply_settings(new_settings)
            elif field == "sort_by":
                new_settings = cycle(self.settings, "sort_by")
                self._apply_settings(new_settings)
            elif field == "date_format":
                new_settings = cycle(self.settings, "date_format")
                self._apply_settings(new_settings)
            elif field == "reset":
                self._apply_settings(SETTINGS_DEFAULTS)
            elif field == "date_custom":
                # Free-text — not cycled here
                pass

    def _apply_settings(self, new_settings: MailSettings) -> None:
        self.settings = new_settings
        self._persist_settings(new_settings)
        self._refresh_list()

    def _persist_settings(self, settings: MailSettings) -> None:
        try:
            from owa_mail.config import load_config, save_config  # type: ignore[import]

            config = load_config()
            config.update(to_config_dict(settings))
            save_config(config)
        except Exception:
            pass

    def action_quit(self) -> None:
        self.app.pop_screen()

    # ------------------------------------------------------------------
    # MessageList event handlers
    # ------------------------------------------------------------------

    def on_message_list_item_selected(self, event: MessageList.ItemSelected) -> None:
        self._selected_msg = event.msg
        idx = self._sorted_messages().index(event.msg) if event.msg in self._sorted_messages() else 0
        self.selected = idx

        # Auto-populate reader pane on selection change (when pane visible)
        if self.settings.reading_pane != "off":
            msg_id = event.msg.get("id") or ""
            if msg_id and msg_id in self._body_cache:
                self._show_cached_body(msg_id)

    def on_message_list_item_activated(self, event: MessageList.ItemActivated) -> None:
        self._selected_msg = event.msg
        msg_id = event.msg.get("id") or ""
        if not msg_id:
            return
        if msg_id in self._body_cache:
            self._show_cached_body(msg_id)
        else:
            self._fetch_body(msg_id)

    # ------------------------------------------------------------------
    # Reactives
    # ------------------------------------------------------------------

    def watch_selected(self, value: int) -> None:
        ml = self._message_list()
        if ml is not None and ml.index != value:
            ml.index = value

    def watch_status(self, value: str) -> None:
        try:
            self.query_one("#status-bar", StatusBar).update(value)
        except Exception:
            pass

    def watch_settings(self, value: MailSettings) -> None:
        self._refresh_list()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _message_list(self) -> MessageList | None:
        try:
            return self.query_one("#message-list", MessageList)
        except Exception:
            return None

    def _current_msg(self) -> dict | None:
        ml = self._message_list()
        if ml is not None:
            return ml.current_msg()
        return self._selected_msg

    def _refresh_list(self) -> None:
        """Rebuild the message list from current messages + settings."""
        ml = self._message_list()
        if ml is None:
            return
        sorted_msgs = self._sorted_messages()
        ml.update_messages(sorted_msgs, self.settings)


# ---------------------------------------------------------------------------
# Layout helpers (inner container widgets)
# ---------------------------------------------------------------------------


class _LayoutRight(Horizontal):
    """Horizontal layout: MessageList left, ReaderPane right."""

    def __init__(self, ratio: int, msg_list: MessageList, reader: ReaderPane) -> None:
        super().__init__(id="mail-layout")
        self._ratio = ratio
        self._msg_list = msg_list
        self._reader = reader

    def compose(self) -> ComposeResult:
        self._msg_list.styles.width = f"{self._ratio}%"
        self._reader.styles.width = f"{100 - self._ratio}%"
        yield self._msg_list
        yield self._reader


class _LayoutBottom(Vertical):
    """Vertical layout: MessageList top, ReaderPane bottom."""

    def __init__(self, ratio: int, msg_list: MessageList, reader: ReaderPane) -> None:
        super().__init__(id="mail-layout")
        self._ratio = ratio
        self._msg_list = msg_list
        self._reader = reader

    def compose(self) -> ComposeResult:
        self._msg_list.styles.height = f"{self._ratio}%"
        self._reader.styles.height = f"{100 - self._ratio}%"
        yield self._msg_list
        yield self._reader


class _LayoutOff(Horizontal):
    """Single-pane layout: only the MessageList (no ReaderPane)."""

    def __init__(self, msg_list: MessageList) -> None:
        super().__init__(id="mail-layout")
        self._msg_list = msg_list

    def compose(self) -> ComposeResult:
        yield self._msg_list


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _build_messages_path(params: dict) -> str:
    """Build the Graph messages endpoint path with OData params."""
    from urllib.parse import urlencode

    base = "me/messages"
    if params:
        return f"{base}?{urlencode(params)}"
    return base
