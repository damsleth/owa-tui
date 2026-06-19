"""HomeScreen: tool-select screen shown at owa-tui startup."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static


class HomeScreen(Screen[str]):
    """Tool-select screen that reads the ``SCREEN_REGISTRY`` to list tools.

    The user selects a tool with arrow keys + Enter (or vim j/k).  The screen
    dismisses with the chosen tool key so ``OwaTuiApp.on_mount`` can push the
    appropriate tool screen.

    If no tool screens have been registered yet, a friendly placeholder message
    is shown so the app still launches.
    """

    TITLE = "owa-tui"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def compose(self) -> ComposeResult:
        from owa_tui.screens import registered_tools

        yield Header()
        yield Label("owa-tui — Microsoft 365 terminal UI", id="home-title")
        yield Label("Select a tool to open:", id="home-subtitle")

        tools = registered_tools()
        if tools:
            items = [ListItem(Static(f"{label}  [{key}]"), id=f"tool-{key}") for key, label in tools]
            yield ListView(*items, id="tool-list")
        else:
            yield Label(
                "No tool screens registered yet.\nCalendar, mail, and graph screens are under active development.",
                id="no-tools-label",
            )
        yield Footer()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        try:
            lv = self.query_one("#tool-list", ListView)
            lv.action_cursor_down()
        except Exception:  # pragma: no cover
            pass

    def action_cursor_up(self) -> None:
        try:
            lv = self.query_one("#tool-list", ListView)
            lv.action_cursor_up()
        except Exception:  # pragma: no cover
            pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Push the selected tool screen via the app."""
        event.stop()
        item_id = event.item.id or ""
        if item_id.startswith("tool-"):
            key = item_id[len("tool-"):]
            self.app.push_tool(key)  # type: ignore[attr-defined]
