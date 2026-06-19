"""screen.py — CalScreen: Textual screen for owa-cal calendar browsing.

This module is the primary entry point for the cal screen package.
Compose the two-pane layout (AgendaList + CalDetailPane), wires up all
keybindings, and drives async event loading via ``@work(exclusive=True)``.

Parity target: ``owa_cal.tui`` curses application.
"""

from __future__ import annotations

import asyncio
import urllib.parse
import webbrowser
from typing import Any

from textual import work
from textual.app import ComposeResult, Screen
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, Static

from owa_tui.screens.cal.agenda import AgendaItemDrilled, AgendaItemSelected, AgendaList
from owa_tui.screens.cal.detail import CalDetailPane
from owa_tui.screens.cal.fetch import fetch_events, range_title
from owa_tui.screens.cal.settings import CalSettings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HELP_LINE = (
    "j/k move · enter detail · / search · r refresh"
    " · y respond (a/t/d) · o browser · esc menu · q quit"
)

_VALID_DAY_RANGES = ("today", "week", "month")

_TOP_MENU_ITEMS = [
    ("Resume", "resume"),
    ("Settings", "settings"),
    ("Help", "help"),
    ("Quit", "quit"),
]

_SETTINGS_FIELDS = [
    ("reading_pane", "Reading pane"),
    ("split_ratio", "Split ratio"),
    ("day_range", "Day range"),
    ("show_declined", "Show declined"),
    ("event_detail", "Event detail"),
    ("_reset", "Reset to defaults"),
    ("_back", "Back"),
]

_RESPOND_KEYS: dict[str, str] = {
    "a": "accept",
    "t": "tentative",
    "d": "decline",
}


# ---------------------------------------------------------------------------
# Search modal
# ---------------------------------------------------------------------------


class _SearchInput(Screen[str]):
    """Tiny modal to capture a search query."""

    DEFAULT_CSS = """
    _SearchInput {
        align: center middle;
    }
    #search-box {
        width: 50;
        border: solid $border;
        background: $surface;
        padding: 1 2;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Static(id="search-box"):
            yield Label("Search: (Enter to confirm, Esc to cancel)")
            yield Input(placeholder="subject or attendee…", id="search-input")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss("")


# ---------------------------------------------------------------------------
# Settings overlay (cal-specific)
# ---------------------------------------------------------------------------


class _CalSettingsOverlay(Screen[str]):
    """Two-level settings overlay for CalScreen."""

    DEFAULT_CSS = """
    _CalSettingsOverlay {
        align: center middle;
    }
    #cal-overlay-box {
        width: 55;
        height: auto;
        border: solid $border;
        background: $surface;
        padding: 1 2;
    }
    .overlay-title { color: $primary; text-style: bold; }
    .overlay-item { color: $text; }
    .overlay-item-selected { color: $primary; text-style: bold; }
    .overlay-hint { color: $text-muted; margin-top: 1; }
    """

    BINDINGS = [
        Binding("up", "move_up", "Up", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("enter", "select", "Select"),
        Binding("escape", "back_or_close", "Back/Close"),
    ]

    def __init__(self, settings: CalSettings) -> None:
        super().__init__()
        self._settings = settings
        self._screen = "top"  # 'top' or 'settings'
        self._cursor = 0

    def compose(self) -> ComposeResult:
        with Static(id="cal-overlay-box"):
            yield Label("owa-cal — menu", classes="overlay-title")
            yield Static(id="cal-menu-items")
            yield Label("↑/↓ move  Enter select  Esc back", classes="overlay-hint")

    def on_mount(self) -> None:
        self._refresh()

    def _items(self) -> list[tuple[str, str]]:
        if self._screen == "settings":
            return _SETTINGS_FIELDS
        return _TOP_MENU_ITEMS

    def _refresh(self) -> None:
        items = self._items()
        cursor = self._cursor
        container = self.query_one("#cal-menu-items", Static)
        lines = []
        for i, (label, action) in enumerate(items):
            prefix = "▶ " if i == cursor else "  "
            css = "overlay-item-selected" if i == cursor else "overlay-item"
            if self._screen == "settings" and action not in ("_reset", "_back"):
                val = getattr(self._settings, label, "")
                display = f"{prefix}{label.replace('_', ' ').title()}: {val}"
            else:
                display = f"{prefix}{label}"
            lines.append(f"[{css}]{display}[/{css}]")
        container.update("\n".join(lines))

    def action_move_up(self) -> None:
        count = len(self._items())
        self._cursor = max(0, self._cursor - 1) if count else 0
        self._refresh()

    def action_move_down(self) -> None:
        count = len(self._items())
        self._cursor = min(count - 1, self._cursor + 1) if count else 0
        self._refresh()

    def action_select(self) -> None:
        items = self._items()
        if not items:
            return
        idx = max(0, min(self._cursor, len(items) - 1))
        field, action = items[idx]

        if self._screen == "top":
            if action == "settings":
                self._screen = "settings"
                self._cursor = 0
                self._refresh()
            else:
                self.dismiss(action)
            return

        # Settings screen
        if action == "_reset":
            self.dismiss("reset")
        elif action == "_back":
            self._screen = "top"
            self._cursor = 0
            self._refresh()
        else:
            self._settings = self._settings.cycle(field)
            self._refresh()
            self.dismiss(f"cycle:{field}")

    def action_back_or_close(self) -> None:
        if self._screen == "settings":
            self._screen = "top"
            self._cursor = 0
            self._refresh()
        else:
            self.dismiss("resume")


# ---------------------------------------------------------------------------
# CalScreen
# ---------------------------------------------------------------------------


class CalScreen(Screen):
    """Main owa-cal Textual Screen — agenda list + detail pane.

    Parameters
    ----------
    config:
        owa-tools config dict (used to load persisted settings).
    access_token:
        Bearer token for Graph API calls.
    api_base:
        Base URL for the Graph API.
    debug:
        Enable verbose owa-tools API logging.
    day_range:
        Override the persisted ``day_range`` setting on startup.
    """

    TITLE = "owa-cal"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("y", "respond_arm", "Respond", show=False),
        Binding("a", "respond_key('a')", "Accept", show=False),
        Binding("t", "respond_key('t')", "Tentative", show=False),
        Binding("d", "respond_key('d')", "Decline", show=False),
        Binding("o", "open_browser", "Open", show=False),
        Binding("escape", "open_menu", "Menu", show=False),
        Binding("/", "search", "Search", show=False),
        Binding("left", "back_to_list", "Back", show=False),
        Binding("h", "back_to_list", "Back", show=False),
    ]

    _status: reactive[str] = reactive("")

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        access_token: str = "",
        api_base: str = "https://outlook.office.com/api/v2.0",
        *,
        debug: bool = False,
        day_range: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = config or {}
        self._access_token = access_token
        self._api_base = api_base
        self._debug = debug

        self._settings = CalSettings.from_config(self._config)
        if day_range in _VALID_DAY_RANGES:
            self._settings = CalSettings(**{**self._settings.__dict__, "day_range": day_range})

        self._events: list[dict[str, Any]] = []
        self._search: str = ""
        self._respond_mode: bool = False

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _make_layout(self) -> Widget:
        """Build the pane layout according to current settings."""
        rp = self._settings.reading_pane
        ratio = self._settings.split_ratio

        agenda = AgendaList(id="agenda-list")
        detail = CalDetailPane(id="detail-pane")

        if rp == "right":
            agenda.styles.width = f"{ratio}%"
            detail.styles.width = f"{100 - ratio}%"
            return Horizontal(agenda, detail, id="main-container")
        if rp == "bottom":
            agenda.styles.height = f"{ratio}%"
            detail.styles.height = f"{100 - ratio}%"
            return Vertical(agenda, detail, id="main-container")
        # 'off' — detail hidden
        return Horizontal(agenda, id="main-container")

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Label(range_title(self._settings.day_range), id="cal-header")
        yield self._make_layout()
        yield Label(HELP_LINE, id="cal-footer")
        yield Label("", id="cal-status")

    def on_mount(self) -> None:
        self.load_events()

    # ------------------------------------------------------------------
    # Reactive watcher
    # ------------------------------------------------------------------

    def watch__status(self, value: str) -> None:
        try:
            self.query_one("#cal-status", Label).update(value)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _agenda(self) -> AgendaList:
        return self.query_one("#agenda-list", AgendaList)

    def _detail(self) -> CalDetailPane | None:
        try:
            return self.query_one("#detail-pane", CalDetailPane)
        except Exception:
            return None

    def _current_event(self) -> dict[str, Any] | None:
        return self._agenda().current_item()

    def _refresh_detail(self) -> None:
        detail = self._detail()
        if detail is None:
            return
        ev = self._current_event()
        detail.update_event(ev, self._settings.event_detail)

    def _update_header(self) -> None:
        try:
            self.query_one("#cal-header", Label).update(
                range_title(self._settings.day_range)
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    @work(exclusive=True)
    async def load_events(self) -> None:
        """Async worker: fetch events and update the UI."""
        events, err = await fetch_events(
            self._access_token,
            self._api_base,
            self._settings.day_range,
            self._settings.show_declined,
            self._search,
            self._debug,
        )
        self._events = events
        self._status = err or ""
        agenda = self._agenda()
        agenda.update_rows(events, show_date=self._settings.day_range != "today")
        if self._current_event() is not None:
            self._refresh_detail()

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_agenda_item_selected(self, message: AgendaItemSelected) -> None:
        """Update the detail pane when selection changes."""
        message.stop()
        if not self._respond_mode:
            self._refresh_detail()

    def on_agenda_item_drilled(self, message: AgendaItemDrilled) -> None:
        """Handle Enter/→/l in the agenda list."""
        message.stop()
        if self._settings.reading_pane == "off":
            self._status = "enable the reading pane (Esc → Settings) to view details"
            return
        detail = self._detail()
        if detail is not None:
            self._refresh_detail()
            detail.focus()
            self._status = "detail focus — j/k scroll · h/← back"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        """r — re-fetch events."""
        self.load_events()

    def action_search(self) -> None:
        """/ — open search modal."""

        def _handle_result(query: str) -> None:
            self._search = query or ""
            self.load_events()

        self.push_screen(_SearchInput(), _handle_result)

    def action_respond_arm(self) -> None:
        """y — arm the respond mode chord."""
        ev = self._current_event()
        if ev is None:
            self._respond_mode = False
            self._status = "no event selected"
            return
        self._respond_mode = True
        self._status = "respond: (a)ccept · (t)entative · (d)ecline · any other key cancels"

    def action_respond_key(self, key: str) -> None:
        """a / t / d — execute respond action if in respond mode."""
        if not self._respond_mode:
            return
        self._respond_mode = False
        action = _RESPOND_KEYS.get(key)
        if action is None:
            self._status = "respond cancelled"
            return
        self._do_respond(action)

    def on_key(self, event: Any) -> None:
        """Intercept keys when respond mode is armed."""
        if self._respond_mode:
            key = event.key
            if key in _RESPOND_KEYS:
                return
            self._respond_mode = False
            self._status = "respond cancelled"
            event.stop()

    @work(exclusive=True)
    async def _do_respond(self, action: str) -> None:
        """Async worker: POST a calendar respond action."""
        ev = self._current_event()
        if ev is None:
            self._status = "no event selected"
            return

        event_id: str = ev.get("id") or ""
        if not event_id:
            self._status = "event has no id"
            return

        subject: str = ev.get("subject") or ""
        rest_map = {
            "accept": "accept",
            "tentative": "tentativelyaccept",
            "decline": "decline",
        }
        rest_action = rest_map[action]
        safe_id = urllib.parse.quote(event_id, safe="")
        endpoint = f"me/events/{safe_id}/{rest_action}"
        body = {"Comment": "", "SendResponse": True}

        try:
            from owa_cal.api import OwaError, api_request  # type: ignore[import]

            def _call() -> Any:
                return api_request(
                    "POST",
                    self._api_base,
                    endpoint,
                    self._access_token,
                    body=body,
                    debug=self._debug,
                )

            result = await asyncio.to_thread(_call)

            if result is None:
                self._status = "respond failed"
                return

            self._status = f"{action}ed: {subject[:30]}"
            self.load_events()

        except Exception as exc:
            from owa_cal.api import OwaError  # type: ignore[import]

            if isinstance(exc, OwaError):
                self._status = f"respond failed: {exc}"
            else:
                self._status = f"respond failed: {exc}"

    def action_open_browser(self) -> None:
        """o — open the selected event in a web browser."""
        ev = self._current_event()
        if ev is None:
            self._status = "no event selected"
            return
        link = ev.get("webLink") or ev.get("web_link") or ""
        if link:
            try:
                webbrowser.open(link)
                self._status = "opened in browser"
            except Exception:
                self._status = "could not open browser"
        else:
            self._status = "no web link for this event"

    def action_open_menu(self) -> None:
        """Esc — open the settings overlay."""
        overlay = _CalSettingsOverlay(self._settings)

        def _handle(result: str) -> None:
            if result == "quit":
                self.app.exit()
            elif result == "help":
                self._status = HELP_LINE
            elif result == "resume":
                pass
            elif result == "reset":
                self._settings = CalSettings()
                self._persist_settings()
                self._update_header()
                self._refresh_detail()
                self.load_events()
            elif result and result.startswith("cycle:"):
                field = result[len("cycle:"):]
                self._settings = overlay._settings
                self._persist_settings()
                self._update_header()
                if field in ("day_range", "show_declined"):
                    self.load_events()
                else:
                    self._refresh_detail()

        self.push_screen(overlay, _handle)

    def action_back_to_list(self) -> None:
        """h / ← — return focus to the agenda list from the detail pane."""
        self._agenda().focus()
        self._status = ""

    def action_quit(self) -> None:
        self.app.exit()

    # ------------------------------------------------------------------
    # Resize
    # ------------------------------------------------------------------

    def on_resize(self, event: Any) -> None:
        self.refresh(layout=True)

    # ------------------------------------------------------------------
    # Settings persistence (best-effort, never crashes TUI)
    # ------------------------------------------------------------------

    def _persist_settings(self) -> None:
        try:
            from owa_cal.config import save_config  # type: ignore[import]

            patch = self._settings.to_config_patch()
            save_config(patch)
        except Exception:
            pass
