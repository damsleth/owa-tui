"""thread.py — OwaThreadScreen: read-only scrollable message thread base.

Designed as a leaf screen pushed on top of OwaListScreen consumers (e.g.
TeamsScreen). Displays an ordered list of messages rendered as Rich-markup
blocks inside a VerticalScroll container.

Contract
--------
Subclass ``OwaThreadScreen`` and implement the two abstract hooks:

    async def fetch_messages(self) -> list[dict]:
        \"\"\"Return the ordered message list for this thread.  Called in a
        @work(thread=True) worker.  Raise on unrecoverable error; return []
        for an empty thread.  Do NOT touch Textual state here — the base
        class marshals results back to the main thread.\"\"\"

    def render_message(self, msg: dict) -> str:
        \"\"\"Return the Rich-markup string for one message block (sender, time,
        body etc.).  Called on the main thread, safe to call app state.\"\"\"

All other behaviour (layout, scroll, breadcrumb, keybindings, StatusBar,
empty + error handling) is handled here and should not be re-implemented in
concrete subclasses.

Optional overridable hooks
--------------------------
- ``on_messages_loaded(messages)`` — called on the main thread after the
  worker delivers results; default is a no-op.  Override to post-process or
  set additional state before the container is filled.
- ``help_text()`` — status-bar text shown for '?'.

Constructor parameters
----------------------
config : dict
    owa-tools config dict (forwarded to auth helper).  POSITIONAL — pass as
    first positional argument so the signature matches OwaListScreen and the
    test-construction invariant in src/tests/test_screen_construction.py.
tool_name : str
    Name used when minting auth tokens (e.g. 'owa-teams').
audience : str
    Auth audience ('outlook' or 'graph').
title : str
    Screen TITLE override (defaults to tool_name).
breadcrumb : str
    Label shown at the top of the thread, e.g. the chat subject.
debug : bool
    Enable verbose adapter logging.
initial_messages : list[dict] | None
    Pre-populated messages (skip fetch; for tests / offline mode).
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, RichLog

from owa_tui.widgets.status_bar import StatusBar

# ---------------------------------------------------------------------------
# THREAD_BINDINGS — scroll + back + quit
# ---------------------------------------------------------------------------

THREAD_BINDINGS: list[Binding] = [
    # --- vertical scroll ---------------------------------------------------
    Binding("j", "scroll_down_line", "Down", show=False),
    Binding("down", "scroll_down_line", "Down", show=False),
    Binding("k", "scroll_up_line", "Up", show=False),
    Binding("up", "scroll_up_line", "Up", show=False),
    Binding("d", "scroll_down_page", "Page Down", show=False),
    Binding("pagedown", "scroll_down_page", "Page Down", show=False),
    Binding("u", "scroll_up_page", "Page Up", show=False),
    Binding("pageup", "scroll_up_page", "Page Up", show=False),
    Binding("g", "scroll_top", "Top", show=False),
    Binding("G", "scroll_bottom", "Bottom", show=False),
    # --- back (to calling screen) ----------------------------------------
    Binding("h", "pop_back", "Back"),
    Binding("escape", "pop_back", "Back"),
    Binding("left", "pop_back", "Back", show=False),
    # --- universal --------------------------------------------------------
    Binding("r", "refresh", "Refresh"),
    Binding("q", "quit", "Quit"),
]


# ---------------------------------------------------------------------------
# OwaThreadScreen
# ---------------------------------------------------------------------------


class OwaThreadScreen(Screen[None]):
    """Generic read-only scrollable message thread base screen.

    Subclass this and implement:
        async def fetch_messages(self) -> list[dict]
        def render_message(self, msg: dict) -> str

    See module docstring for the full API.
    """

    BINDINGS: list[Binding] = list(THREAD_BINDINGS)  # type: ignore[assignment]

    # -------------------------------------------------------------------------
    # Constructor — config is POSITIONAL (guarded by test_screen_construction.py)
    # -------------------------------------------------------------------------

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        tool_name: str = "owa-thread",
        audience: str = "graph",
        title: str = "",
        breadcrumb: str = "",
        debug: bool = False,
        initial_messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = config or {}
        self._tool_name = tool_name
        self._audience = audience
        self._screen_title = title or tool_name
        self._breadcrumb = breadcrumb
        self._debug = debug

        # Pre-populated messages bypass the fetch worker (tests / offline mode)
        if initial_messages is not None:
            self._messages: list[dict] = list(initial_messages)
            self._preloaded = True
        else:
            self._messages = []
            self._preloaded = False

        self._status: str = ""

    # -------------------------------------------------------------------------
    # Abstract hooks — subclass MUST implement
    # -------------------------------------------------------------------------

    async def fetch_messages(self) -> list[dict]:
        """Fetch the ordered message list for this thread.

        Runs inside a @work(thread=True) worker — do NOT touch UI state.
        Raise on unrecoverable error; return [] for an empty thread.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement fetch_messages()")

    def render_message(self, msg: dict) -> str:
        """Return the Rich-markup display string for one message block.

        Called on the main thread.  Typical implementation:

            sender = msg.get("from", {}).get("user", {}).get("displayName", "?")
            ts     = msg.get("createdDateTime", "")[:16]
            body   = msg.get("body", {}).get("content", "")
            return f"[bold]{sender}[/bold]  [dim]{ts}[/dim]\\n{body}\\n"
        """
        raise NotImplementedError(f"{type(self).__name__} must implement render_message()")

    # -------------------------------------------------------------------------
    # Optional overridable hooks
    # -------------------------------------------------------------------------

    def on_messages_loaded(self, messages: list[dict]) -> None:
        """Called on the main thread after the worker delivers results.

        Default: no-op.  Override to post-process or set additional state
        before the container is filled.
        """

    def help_text(self) -> str:
        """Status-bar text shown for '?'."""
        return "j/k scroll  g/G top/bottom  r refresh  h/Esc back  q quit"

    # -------------------------------------------------------------------------
    # Composition
    # -------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(self._breadcrumb or self._screen_title, id="thread-breadcrumb")
        yield RichLog(id="thread-log", highlight=True, markup=True, wrap=True)
        yield StatusBar(self._status, id="owa-status-bar")
        yield Footer()

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def on_mount(self) -> None:
        self.title = self._screen_title
        if self._preloaded:
            self._apply_messages(self._messages)
        else:
            self._load_messages()

    # -------------------------------------------------------------------------
    # Worker
    # -------------------------------------------------------------------------

    @work(thread=True)
    def _load_messages(self) -> None:
        """Background thread: call fetch_messages() and marshal results to the main thread."""
        import asyncio  # noqa: PLC0415

        self.app.call_from_thread(self._set_status, "Loading…")
        try:
            messages = asyncio.run(self.fetch_messages())
        except Exception as exc:
            err = str(exc)
            self.app.call_from_thread(self._set_status, f"error: {err}")
            return
        self.app.call_from_thread(self._apply_messages, messages)

    # -------------------------------------------------------------------------
    # Main-thread helpers (always called on the main thread)
    # -------------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        """Update the StatusBar text.  Must be called on the main thread."""
        self._status = text
        try:
            self.query_one("#owa-status-bar", StatusBar).update(text)
        except Exception:
            pass

    def _apply_messages(self, messages: list[dict]) -> None:
        """Populate the RichLog with rendered messages.  Must be on the main thread."""
        self._messages = list(messages)
        self.on_messages_loaded(messages)

        log = self._thread_log()
        if log is None:
            return

        log.clear()

        if not messages:
            log.write("[dim](no messages)[/dim]")
            self._set_status("0 messages")
            return

        for msg in messages:
            try:
                rendered = self.render_message(msg)
            except Exception as exc:
                rendered = f"[red](render error: {exc})[/red]"
            log.write(rendered)

        n = len(messages)
        noun = "message" if n == 1 else "messages"
        self._set_status(f"{n} {noun}")

        # Scroll to bottom so the most-recent message is visible by default
        log.scroll_end(animate=False)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _thread_log(self) -> RichLog | None:
        try:
            return self.query_one("#thread-log", RichLog)
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Actions (implement THREAD_BINDINGS action names)
    # -------------------------------------------------------------------------

    def action_scroll_down_line(self) -> None:
        log = self._thread_log()
        if log is not None:
            log.scroll_down(animate=False)

    def action_scroll_up_line(self) -> None:
        log = self._thread_log()
        if log is not None:
            log.scroll_up(animate=False)

    def action_scroll_down_page(self) -> None:
        log = self._thread_log()
        if log is not None:
            log.scroll_page_down(animate=False)

    def action_scroll_up_page(self) -> None:
        log = self._thread_log()
        if log is not None:
            log.scroll_page_up(animate=False)

    def action_scroll_top(self) -> None:
        log = self._thread_log()
        if log is not None:
            log.scroll_home(animate=False)

    def action_scroll_bottom(self) -> None:
        log = self._thread_log()
        if log is not None:
            log.scroll_end(animate=False)

    def action_pop_back(self) -> None:
        """Pop this thread screen and return to the caller (chat list)."""
        self.app.pop_screen()

    def action_refresh(self) -> None:
        """Re-fetch and re-render the thread."""
        self._messages = []
        log = self._thread_log()
        if log is not None:
            log.clear()
        self._load_messages()

    def action_quit(self) -> None:
        self.app.exit()
