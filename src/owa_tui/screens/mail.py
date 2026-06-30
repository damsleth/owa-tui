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
    """Scrollable reading pane for a single message.

    When focused (Tab from the list), j/k and u/d scroll this pane with the
    same keys that move/page the list — they bind on the focused widget so
    they intercept before the screen-level list bindings.
    """

    DEFAULT_CSS = """
    ReaderPane {
        overflow-y: scroll;
        padding: 0 1;
        border-left: solid $border;
    }
    """

    BINDINGS = [
        Binding("j", "scroll_line_down", "Down", show=False),
        Binding("down", "scroll_line_down", "Down", show=False),
        Binding("k", "scroll_line_up", "Up", show=False),
        Binding("up", "scroll_line_up", "Up", show=False),
        Binding("d", "scroll_half_down", "Half page down", show=False),
        Binding("u", "scroll_half_up", "Half page up", show=False),
        Binding("g", "scroll_to_top", "Top", show=False),
        Binding("G", "scroll_to_bottom", "Bottom", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static("", id="reader-content")

    def _half(self) -> int:
        return max(1, (self.size.height or 10) // 2)

    def action_scroll_line_down(self) -> None:
        self.scroll_down(animate=False)

    def action_scroll_line_up(self) -> None:
        self.scroll_up(animate=False)

    def action_scroll_half_down(self) -> None:
        self.scroll_relative(y=self._half(), animate=False)

    def action_scroll_half_up(self) -> None:
        self.scroll_relative(y=-self._half(), animate=False)

    def action_scroll_to_top(self) -> None:
        self.scroll_home(animate=False)

    def action_scroll_to_bottom(self) -> None:
        self.scroll_end(animate=False)

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


class FolderList(ListView):
    """Left-hand folder panel. Posts ``FolderSelected`` when a folder is opened."""

    DEFAULT_CSS = """
    FolderList {
        width: 26;
        border-right: solid $border;
    }
    """

    @dataclass
    class FolderSelected(Message):
        folder: dict

    def __init__(self, folders: list[dict] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._folders: list[dict] = list(folders or [])

    def set_folders(self, folders: list[dict]) -> None:
        self._folders = list(folders)
        self._rebuild()

    def current_folder(self) -> dict | None:
        idx = self.index
        if idx is None or idx >= len(self._folders):
            return None
        return self._folders[idx]

    def _rebuild(self) -> None:
        self.clear()
        if not self._folders:
            self.append(ListItem(Static("(loading folders…)", id="no-folders-label")))
            return
        for f in self._folders:
            unread = f.get("unread") or 0
            badge = f" [b]({unread})[/b]" if unread else ""
            self.append(ListItem(Label(f"{f.get('name', '?')}{badge}")))

    def on_mount(self) -> None:
        self._rebuild()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        f = self.current_folder()
        if f is not None:
            self.post_message(self.FolderSelected(f))


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
        Binding("F", "toggle_folders", "Folders"),
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
        # Folder panel + pagination state
        self._folder_id: str | None = None  # None → default "me/messages" view
        self._folders_loaded = False
        self._has_more = True  # another page may exist
        self._loading_more = False  # guard against overlapping page fetches

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
        yield self._build_root()
        yield StatusBar(self.status, id="status-bar")
        yield Footer()

    def _build_root(self) -> Any:
        """Outer container: optional FolderList left of the list+reader layout."""
        inner = self._build_layout()
        if self.settings.show_folders:
            return Horizontal(FolderList(id="folder-list"), inner, id="mail-root")
        return Horizontal(inner, id="mail-root")

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
            if self.settings.show_folders:
                self._fetch_folders()

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
        skip: int = 0,
        append: bool = False,
    ) -> None:
        """Fetch a page of messages from Graph in a background thread.

        ``skip``/``append`` drive pagination: when the cursor hits the last
        row, the next $skip page is fetched and appended instead of replacing.
        """
        if not append:
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
                if append:
                    self.app.call_from_thread(self._finish_more)
                return

            params = build_list_query(
                search=search,
                since=since,
                until=until,
                limit=PAGE_SIZE,
            )
            if skip:
                params = {**params, "$skip": skip}
            path = self._messages_path(params)
            from owa_tui import fixtures  # noqa: PLC0415

            raw = fixtures.load("mail")
            if raw is None:
                raw = api_get(self._api_base, path, token, debug=self._debug)
            if raw is None:
                if append:
                    self.app.call_from_thread(self._finish_more)
                elif search:
                    self.app.call_from_thread(self._on_search_failed)
                else:
                    self.app.call_from_thread(
                        lambda: setattr(self, "status", "fetch failed: no data returned")
                    )
                return

            msgs = normalize_messages(raw, keep_body=False)
            if append:
                self.app.call_from_thread(self._append_messages, msgs)
            else:
                self.app.call_from_thread(self._apply_messages, msgs, search)
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(lambda: setattr(self, "status", f"error: {err}"))
            if append:
                self.app.call_from_thread(self._finish_more)

    def _messages_path(self, params: dict) -> str:
        """Endpoint for the current folder (or the default mailbox view)."""
        if self._folder_id:
            from owa_mail.folders import (
                folder_messages_path,  # type: ignore[import]  # noqa: PLC0415
            )

            base = folder_messages_path(self._folder_id)
            if params:
                from urllib.parse import urlencode  # noqa: PLC0415

                return f"{base}?{urlencode(params)}"
            return base
        return _build_messages_path(params)

    @work(thread=True)
    def _fetch_folders(self) -> None:
        """Load the mail-folder list for the side panel (background thread)."""
        try:
            from owa_mail.api import api_get, build_query  # type: ignore[import]
            from owa_mail.folders import normalize_folders  # type: ignore[import]

            token = self._get_token_sync()
            if not token:
                return
            q = build_query(
                {"$select": "Id,DisplayName,UnreadItemCount,TotalItemCount", "$top": 100}
            )
            from owa_tui import fixtures  # noqa: PLC0415

            raw = fixtures.load("mail_folders")
            if raw is None:
                raw = api_get(self._api_base, f"me/MailFolders?{q}", token, debug=self._debug)
            if raw is None:
                return
            folders = normalize_folders(raw)
            self.app.call_from_thread(self._apply_folders, folders)
        except Exception:
            pass  # folder panel is best-effort; absence just shows "(loading…)"

    def _apply_folders(self, folders: list[dict]) -> None:
        self._folders_loaded = True
        try:
            self.query_one("#folder-list", FolderList).set_folders(folders)
        except Exception:
            pass

    def _get_token_sync(self) -> str:
        """Mint a fresh auth token via owa-piggy (runs in worker thread)."""
        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        return access_token_for(self._config, tool_name="owa-mail", audience="outlook")

    def _apply_messages(self, msgs: list[dict], search: str) -> None:
        """Called on main thread after a fresh (non-append) list fetch."""
        self.messages = msgs
        self.search = search
        self.selected = 0
        self._body_cache = {}
        self._has_more = len(msgs) >= PAGE_SIZE
        self._loading_more = False
        self._refresh_list()
        count = len(msgs)
        self.status = f"{count} message{'s' if count != 1 else ''}"

    def _append_messages(self, msgs: list[dict]) -> None:
        """Append the next page, de-duped by id; keep the cursor where it was."""
        self._loading_more = False
        existing = {m.get("id") for m in self.messages}
        fresh = [m for m in msgs if m.get("id") not in existing]
        # A short page (or nothing new) means we've reached the end.
        self._has_more = len(msgs) >= PAGE_SIZE and bool(fresh)
        if not fresh:
            return
        ml = self._message_list()
        keep = ml.index if ml is not None else None
        self.messages = self.messages + fresh
        self._refresh_list()
        if ml is not None and keep is not None:
            ml.index = keep
            self.selected = keep
        self.status = f"{len(self.messages)} messages"

    def _finish_more(self) -> None:
        """Clear the in-flight page guard after a failed/empty append."""
        self._loading_more = False
        self._has_more = False

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
            from owa_tui import fixtures  # noqa: PLC0415

            raw = fixtures.load("mail_body")
            if raw is None:
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
        from owa_tui import fixtures  # noqa: PLC0415

        if fixtures.enabled():
            return
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
            self._maybe_load_more(ml)

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
            self._maybe_load_more(ml)

    def _maybe_load_more(self, ml: MessageList) -> None:
        """Fetch the next page when the cursor reaches the last row."""
        if self._messages_preloaded:  # tests / fixture preload: no live paging
            return
        if not self._has_more or self._loading_more:
            return
        idx = ml.index
        if idx is None or idx < len(self.messages) - 1:
            return
        self._loading_more = True
        self.status = "Loading more…"
        self._fetch_list(search=self.search, skip=len(self.messages), append=True)

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
            self._maybe_load_more(ml)

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
        self._reselect(msg)  # keep this email selected; only its read-state changed
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

    def action_toggle_folders(self) -> None:
        """F: show/hide the folder panel (persisted; takes effect immediately)."""
        self._apply_settings(cycle(self.settings, "show_folders"))

    def _sync_folder_pane(self) -> None:
        """Mount or remove the FolderList to match ``settings.show_folders``."""
        try:
            root = self.query_one("#mail-root", Horizontal)
        except Exception:
            return
        panes = list(self.query("#folder-list"))
        if self.settings.show_folders and not panes:
            root.mount(FolderList(id="folder-list"), before=0)
            if not self._folders_loaded and not self._messages_preloaded:
                self._fetch_folders()
        elif not self.settings.show_folders and panes:
            panes[0].remove()

    def action_open_menu(self) -> None:
        settings_fields = [
            ("reading_pane", "Reading pane"),
            ("split_ratio", "Split ratio"),
            ("sort_by", "Sort by"),
            ("date_format", "Date format"),
            ("show_folders", "Folder panel"),
            ("_reset", "Reset to defaults"),
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
            settings=self.settings,
            cycle_fn=cycle,
            on_change=self._on_setting_changed,
        )
        self.app.push_screen(overlay, self._handle_overlay)

    def _on_setting_changed(self, _field: str, new_settings: MailSettings) -> None:
        """Live callback from the overlay each time a field is cycled."""
        self._apply_settings(new_settings)

    def _handle_overlay(self, result: str) -> None:
        if result == "resume" or result is None:
            return
        if result == "quit":
            self.app.exit()
            return
        if result == "help":
            self.status = "j/k move  g/G top/bottom  Enter open  / search  r toggle-read  o browser"
            return
        if result == "reset":
            self._apply_settings(SETTINGS_DEFAULTS)

    def _apply_settings(self, new_settings: MailSettings) -> None:
        old = self.settings
        self.settings = new_settings
        self._persist_settings(new_settings)
        self._refresh_list()
        self._sync_folder_pane()
        # Apply layout-affecting settings live, without re-entering the screen.
        if new_settings.reading_pane != old.reading_pane:
            self._rebuild_layout()
        elif new_settings.split_ratio != old.split_ratio:
            self._resize_panes()

    def _resize_panes(self) -> None:
        """Update split sizes in place (no rebuild → keeps selection + body)."""
        if self.settings.reading_pane == "off":
            return
        ml = self._message_list()
        try:
            reader = self.query_one("#reader-pane", ReaderPane)
        except Exception:
            return
        if ml is None:
            return
        ratio = self.settings.split_ratio
        if self.settings.reading_pane == "right":
            ml.styles.width = f"{ratio}%"
            reader.styles.width = f"{100 - ratio}%"
        else:  # bottom
            ml.styles.height = f"{ratio}%"
            reader.styles.height = f"{100 - ratio}%"

    def _rebuild_layout(self) -> None:
        """Swap the list+reader container when the reading-pane mode changes."""
        sel = self.selected
        shown = self._selected_msg

        async def _swap() -> None:
            try:
                old = self.query_one("#mail-layout")
                root = self.query_one("#mail-root", Horizontal)
            except Exception:
                return
            await old.remove()  # await first so we never have two #mail-layout
            await root.mount(self._build_layout())
            # Defer restore: ListView resets its index during its own mount
            # tick, so set the cursor after the screen settles.
            self.call_after_refresh(self._restore_after_relayout, sel, shown)

        self.run_worker(_swap(), exclusive=True)

    def _restore_after_relayout(self, sel: int | None, shown: dict | None) -> None:
        ml = self._message_list()
        if ml is not None and sel is not None and 0 <= sel < len(self._sorted_messages()):
            ml.index = sel
            self.selected = sel
        if self.settings.reading_pane != "off" and shown:
            msg_id = shown.get("id") or ""
            if msg_id in self._body_cache:
                self._show_cached_body(msg_id)

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

    def on_folder_list_folder_selected(self, event: FolderList.FolderSelected) -> None:
        """Switch the message list to the chosen folder and reload from page 1."""
        folder = event.folder
        self._folder_id = folder.get("id") or folder.get("name") or "Inbox"
        self.folder = folder.get("name") or "Inbox"
        self.search = ""
        self._has_more = True
        self._loading_more = False
        self._fetch_list()
        ml = self._message_list()
        if ml is not None:
            ml.focus()

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

    def _reselect(self, msg: dict) -> None:
        """Restore the cursor onto *msg* after a list rebuild.

        A rebuild clears the ListView (index → None); without this the row
        deselects. Matches by id so the message stays selected even if the
        sort order moved it (e.g. unread_first after toggling read).
        """
        ml = self._message_list()
        msg_id = msg.get("id")
        if ml is None or not msg_id:
            return
        for i, m in enumerate(self._sorted_messages()):
            if m.get("id") == msg_id:
                ml.index = i
                self.selected = i
                break


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
