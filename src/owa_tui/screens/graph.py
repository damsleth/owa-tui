"""Graph explorer screen for owa-tui.

Flagship adapter: 17 FOCI audiences x 4 tiers, per-audience exp-aware token
cache, graceful degradation on AADSTS65002/53003, 3 pagination shapes,
breadcrumb history, query editing, and action keys o/y/c/a/m/D.

All blocking owa-tools/auth calls run in ``@work(thread=True)`` async
workers so the Textual event loop is never stalled.

Registration
-----------
At import time this module calls ``register_screen('graph', ...)`` so
``OwaTuiApp`` can push it when the user selects "Graph" or ``--tool graph``.

Do NOT call ``setup_auth`` or any owa_graph.tui function — this module
uses the stable owa-tools library surface only.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, ListItem, ListView, Static

from owa_tui.graph.actions import (
    action_bookmark,
    action_curl_command,
    action_open_browser,
    action_yank_url,
)
from owa_tui.graph.fetch import AUDIENCE_API_BASE, fetch_items
from owa_tui.graph.nav import Row, on_back, on_drill
from owa_tui.graph.settings import GraphSettings
from owa_tui.graph.state import GraphState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FOOTER_TEXT = (
    "↑↓/jk move  Enter/→/l drill  h/← back  "
    "a audience  / path  e edit query  n next  r refresh  "
    "o Graph Explorer  y yank URL  c curl  m bookmark  D debug  Esc menu  q quit"
)

HELP_LINES = [
    "[bold]Graph Explorer keyboard reference[/bold]",
    "",
    "[bold]Navigation[/bold]",
    "  ↑/↓  j/k      Move cursor",
    "  Enter/→/l     Drill into item",
    "  h/←/Backspace  Go back",
    "  PgUp/PgDn/Space  Page scroll",
    "  g / G         Top / bottom of list",
    "",
    "[bold]Audience & path[/bold]",
    "  a              Switch audience (17 FOCI audiences across 4 tiers)",
    "  /              Jump to path (free-text input)",
    "  e              Edit query params",
    "  n              Next page",
    "  r              Re-fetch current path",
    "",
    "[bold]Clipboard & bookmarks[/bold]",
    "  y              Yank URL (pbcopy/xclip/xsel)",
    "  c              Copy curl command to debug buffer",
    "  o              Open Graph Explorer (graph audience only)",
    "  m              Bookmark current path",
    "",
    "[bold]General[/bold]",
    "  Esc            Toggle menu",
    "  D              Debug overlay (last 400 chars of debug buffer)",
    "  q              Quit",
]

# 17 FOCI audiences in tier order
AUDIENCES = [
    # Tier A
    "graph",
    "outlook",
    "outlook365",
    "azure",
    "powerbi",
    # Tier B
    "flow",
    "manage",
    "substrate",
    "devops",
    # Tier C
    "teams",
    "ic3",
    "csa",
    "presence",
    "uis",
    # Tier D
    "keyvault",
    "storage",
    "sql",
]

_TIER_LABELS = {
    "graph": "A",
    "outlook": "A",
    "outlook365": "A",
    "azure": "A",
    "powerbi": "A",
    "flow": "B",
    "manage": "B",
    "substrate": "B",
    "devops": "B",
    "teams": "C",
    "ic3": "C",
    "csa": "C",
    "presence": "C",
    "uis": "C",
    "keyvault": "D",
    "storage": "D",
    "sql": "D",
}


def _audience_label(audience: str) -> str:
    tier = _TIER_LABELS.get(audience, "?")
    return f"[{tier}] {audience}"


# ---------------------------------------------------------------------------
# GraphScreen
# ---------------------------------------------------------------------------


class GraphScreen(Screen[None]):
    """Graph explorer screen — flagship owa-tui adapter.

    Parameters
    ----------
    config:
        owa-tools config dict.
    debug:
        Enable verbose owa-tools API logging.
    """

    TITLE = "owa-tui — Graph Explorer"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "toggle_menu", "Menu"),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("n", "next_page", "Next page", show=False),
        Binding("a", "switch_audience", "Audience", show=False),
        Binding("slash", "jump_path", "Jump to path", show=False),
        Binding("e", "edit_query", "Edit query", show=False),
        Binding("o", "open_browser", "Graph Explorer", show=False),
        Binding("y", "yank_url", "Yank URL", show=False),
        Binding("c", "curl_command", "Curl", show=False),
        Binding("m", "bookmark", "Bookmark", show=False),
        Binding("D", "debug_overlay", "Debug", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("l", "drill", "Drill", show=False),
        Binding("h", "back", "Back", show=False),
        Binding("enter", "drill", "Drill", show=False),
        Binding("right", "drill", "Drill", show=False),
        Binding("left", "back", "Back", show=False),
        Binding("backspace", "back", "Back", show=False),
    ]

    DEFAULT_CSS = """
    GraphScreen {
        layout: vertical;
    }
    #breadcrumb {
        height: 1;
        background: $boost;
        color: $text-muted;
        padding: 0 1;
    }
    #status-bar {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    #main-area {
        height: 1fr;
    }
    #list-pane {
        width: 60%;
        border-right: solid $border;
    }
    #detail-pane {
        width: 40%;
        overflow-y: scroll;
        padding: 0 1;
    }
    #graph-list {
        height: 1fr;
    }
    #input-bar {
        height: 3;
        display: none;
    }
    #input-bar.visible {
        display: block;
    }
    #debug-overlay {
        height: 10;
        background: $surface;
        border: solid $warning;
        padding: 0 1;
        display: none;
    }
    #debug-overlay.visible {
        display: block;
    }
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config or {}
        self._debug = debug
        self._settings = GraphSettings.from_config(self._config)
        self._state = GraphState(
            config=self._config,
            audience=self._settings.default_audience,
            path=self._settings.default_path,
            debug=debug,
        )
        self._input_mode: str | None = None  # 'path', 'query', 'audience'
        self._show_debug = False

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="breadcrumb")
        with Horizontal(id="main-area"):
            with ScrollableContainer(id="list-pane"):
                yield ListView(id="graph-list")
            with ScrollableContainer(id="detail-pane"):
                yield Static("", id="detail-content")
        yield Static("", id="status-bar")
        yield Input(placeholder="", id="input-bar")
        yield Static("", id="debug-overlay")
        yield Footer()

    def on_mount(self) -> None:
        """Trigger initial data fetch when screen is ready."""
        self._refresh_breadcrumb()
        self._refresh_status()
        self._start_fetch()

    # ------------------------------------------------------------------
    # Async fetch worker
    # ------------------------------------------------------------------

    @work(thread=True)
    def _start_fetch(self) -> None:
        """Fetch items for the current state in a background thread."""
        fetch_items(self._state)
        self.app.call_from_thread(self._apply_fetch_result)

    def _apply_fetch_result(self) -> None:
        """Called on the main event loop after fetch completes."""
        self._refresh_list()
        self._refresh_breadcrumb()
        self._refresh_status()
        self._refresh_detail(None)

    # ------------------------------------------------------------------
    # UI refresh helpers
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        lv = self.query_one("#graph-list", ListView)
        lv.clear()
        for row in self._state.items:
            if isinstance(row, Row):
                label_text = row.label
                if row.dim:
                    label_text = f"[dim]{label_text}[/dim]"
                lv.append(ListItem(Static(label_text)))
            else:
                lv.append(ListItem(Static(str(row))))

    def _refresh_breadcrumb(self) -> None:
        depth = len(self._state.history)
        crumb = f"{self._state.audience}:{self._state.path or '/'}"
        if depth > 0:
            crumb = f"{'… > ' * min(depth, 3)}{crumb}"
        self.query_one("#breadcrumb", Static).update(crumb)

    def _refresh_status(self) -> None:
        self.query_one("#status-bar", Static).update(self._state.status)

    def _refresh_detail(self, item: Row | None) -> None:
        """Update the detail pane with the selected item."""
        pane = self.query_one("#detail-content", Static)
        if item is None:
            # Show first item detail if available
            items = self._state.items
            if items and isinstance(items[0], Row):
                item = items[0]
            else:
                pane.update("")
                return

        if item is None:
            pane.update("")
            return

        lines = [f"[bold]{item.label}[/bold]"]
        if item.drill_target:
            lines.append(f"[dim]target: {item.drill_target}[/dim]")
        lines.append("")
        lines.append(f"drillable: {item.drillable}")
        pane.update("\n".join(lines))

    # ------------------------------------------------------------------
    # Input bar
    # ------------------------------------------------------------------

    def _show_input(self, mode: str, placeholder: str) -> None:
        self._input_mode = mode
        inp = self.query_one("#input-bar", Input)
        inp.placeholder = placeholder
        inp.value = ""
        inp.add_class("visible")
        inp.focus()

    def _hide_input(self) -> None:
        self._input_mode = None
        inp = self.query_one("#input-bar", Input)
        inp.remove_class("visible")
        self.query_one("#graph-list", ListView).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input bar submission for path, query, or audience."""
        value = event.value.strip()
        mode = self._input_mode
        self._hide_input()

        if not value:
            return

        if mode == "path":
            self._state.path = value
            self._state.next_link = None
            self._state.selected = 0
            self._state.top = 0
            self._state.dirty = True
            self._start_fetch()

        elif mode == "query":
            self._state.query = value
            self._state.next_link = None
            self._state.dirty = True
            self._start_fetch()

        elif mode == "audience":
            if value in AUDIENCES:
                self._state.audience = value
                # Set seed path for the new audience
                self._state.path = self._settings.default_path if value == self._settings.default_audience else ""
                self._state.next_link = None
                self._state.dirty = True
                self._state.status = f"switching to {value!r}…"
                self._refresh_status()
                self._start_fetch()
            else:
                self._state.status = f"unknown audience: {value!r}  (valid: {', '.join(AUDIENCES)})"
                self._refresh_status()

    # ------------------------------------------------------------------
    # List view events
    # ------------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update detail pane when cursor moves."""
        event.stop()
        lv = self.query_one("#graph-list", ListView)
        idx = lv.index
        if idx is not None and idx < len(self._state.items):
            item = self._state.items[idx]
            if isinstance(item, Row):
                self._refresh_detail(item)
                self._state.selected = idx

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Drill into item on Enter."""
        event.stop()
        self.action_drill()

    # ------------------------------------------------------------------
    # Navigation actions
    # ------------------------------------------------------------------

    def action_drill(self) -> None:
        lv = self.query_one("#graph-list", ListView)
        idx = lv.index
        if idx is None or idx >= len(self._state.items):
            return
        item = self._state.items[idx]
        if not isinstance(item, Row):
            return
        drilled = on_drill(self._state, item)
        if drilled:
            self._start_fetch()
            self._refresh_breadcrumb()

    def action_back(self) -> None:
        went_back = on_back(self._state)
        if went_back:
            self._refresh_list()
            self._refresh_breadcrumb()
            self._refresh_status()

    def action_refresh(self) -> None:
        self._state.next_link = None
        self._state.selected = 0
        self._state.top = 0
        self._state.dirty = True
        self._start_fetch()

    def action_next_page(self) -> None:
        if self._state.next_link:
            self._state.dirty = True
            self._start_fetch()
        else:
            self._state.status = "no next page"
            self._refresh_status()

    # ------------------------------------------------------------------
    # Audience / path / query input actions
    # ------------------------------------------------------------------

    def action_switch_audience(self) -> None:
        current_idx = AUDIENCES.index(self._state.audience) if self._state.audience in AUDIENCES else 0
        self._show_input("audience", f"audience ({current_idx}: {self._state.audience}) — type name: {', '.join(AUDIENCES[:5])}…")

    def action_jump_path(self) -> None:
        self._show_input("path", f"path (current: {self._state.path or '/'})")

    def action_edit_query(self) -> None:
        self._show_input("query", f"query params (current: {self._state.query or 'none'})")

    # ------------------------------------------------------------------
    # Clipboard / browser / bookmark actions
    # ------------------------------------------------------------------

    def action_open_browser(self) -> None:
        api_base = AUDIENCE_API_BASE.get(self._state.audience, "")
        action_open_browser(self._state, api_base)
        self._refresh_status()

    def action_yank_url(self) -> None:
        api_base = AUDIENCE_API_BASE.get(self._state.audience, "")
        action_yank_url(self._state, api_base)
        self._refresh_status()

    def action_curl_command(self) -> None:
        api_base = AUDIENCE_API_BASE.get(self._state.audience, "")
        action_curl_command(self._state, api_base)
        self._refresh_status()

    def action_bookmark(self) -> None:
        action_bookmark(self._state, self._settings)
        self._refresh_status()

    # ------------------------------------------------------------------
    # Debug overlay
    # ------------------------------------------------------------------

    def action_debug_overlay(self) -> None:
        self._show_debug = not self._show_debug
        overlay = self.query_one("#debug-overlay", Static)
        if self._show_debug:
            buf = self._state.stderr_buf
            snippet = buf[-400:] if len(buf) > 400 else buf
            overlay.update(f"[bold]Debug buffer:[/bold]\n{snippet}")
            overlay.add_class("visible")
        else:
            overlay.remove_class("visible")

    # ------------------------------------------------------------------
    # Menu toggle
    # ------------------------------------------------------------------

    def action_toggle_menu(self) -> None:
        from owa_tui.widgets.settings_overlay import SettingsOverlay

        overlay = SettingsOverlay(
            title_lines=["Graph Explorer — menu"],
            top_items=[
                ("Resume", "resume"),
                ("Settings", "settings"),
                ("Help", "help"),
                ("Quit", "quit"),
            ],
            settings_fields=[
                ("reading_pane", "Reading pane"),
                ("pretty_json", "Pretty JSON (graph only)"),
                ("scope_warnings", "Scope warnings"),
            ],
            settings=self._settings,
        )

        def _on_dismiss(result: str) -> None:
            if result == "quit":
                self.app.exit()
            elif result == "resume":
                pass
            elif result and result.startswith("cycle:"):
                pass

        self.app.push_screen(overlay, _on_dismiss)

    # ------------------------------------------------------------------
    # Cursor movement
    # ------------------------------------------------------------------

    def _lv(self) -> ListView:
        return self.query_one("#graph-list", ListView)

    def action_cursor_down(self) -> None:
        self._lv().action_cursor_down()

    def action_cursor_up(self) -> None:
        self._lv().action_cursor_up()

    def action_cursor_top(self) -> None:
        lv = self._lv()
        lv.index = 0

    def action_cursor_bottom(self) -> None:
        lv = self._lv()
        if self._state.items:
            lv.index = len(self._state.items) - 1

    def action_quit(self) -> None:
        self.app.exit()

    # ------------------------------------------------------------------
    # Key pass-through for PgUp/PgDn/Space
    # ------------------------------------------------------------------

    def on_key(self, event: Any) -> None:
        key = event.key
        lv = self._lv()
        if key == "pageup":
            lv.action_scroll_up()
            event.stop()
        elif key in ("pagedown", "space"):
            lv.action_scroll_down()
            event.stop()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

from owa_tui.screens import register_screen  # noqa: E402

register_screen("graph", "Graph Explorer", GraphScreen)
