"""SettingsOverlay: generic two-level settings modal screen.

Usage
-----
    overlay = SettingsOverlay(
        title_lines=['owa-cal — settings'],
        top_items=[('Resume', 'resume'), ('Settings', 'settings'), ('Quit', 'quit')],
        settings_fields=[('show_declined', 'Show declined'), ('day_range', 'Day range')],
        settings=my_settings_instance,
    )
    self.app.push_screen(overlay, self._handle_overlay_result)

The ``callback`` receives the action string (``'resume'``, ``'quit'``,
``'settings'``, ``'cycle:<field>'``) so the parent screen can act on it.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from owa_tui.widgets.menu_state import MenuState


class SettingsOverlay(ModalScreen[str]):
    """Generic two-level (top / settings) settings overlay.

    Parameters
    ----------
    title_lines:
        Header text lines rendered at the top of the overlay box.
    top_items:
        ``[(label, action_str), ...]`` for the top-level menu.
    settings_fields:
        ``[(field_name, display_label), ...]`` for the settings sub-menu.
    settings:
        The current tool-settings dataclass instance (mutated by cycle actions).
    """

    BINDINGS = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("enter", "select", "Select"),
        Binding("escape", "back_or_close", "Back/Close"),
        Binding("q", "back_or_close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    SettingsOverlay {
        align: center middle;
    }

    SettingsOverlay #overlay-box {
        width: 50;
        height: auto;
        border: solid $border;
        background: $surface;
        padding: 1 2;
    }

    SettingsOverlay .overlay-title {
        color: $primary;
        text-style: bold;
    }

    SettingsOverlay .overlay-item {
        color: $text;
    }

    SettingsOverlay .overlay-item-selected {
        color: $primary;
        text-style: bold;
    }

    SettingsOverlay .overlay-hint {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        title_lines: list[str],
        top_items: list[tuple[str, str]],
        settings_fields: list[tuple[str, str]] | None = None,
        settings: Any = None,
    ) -> None:
        super().__init__()
        self._menu_state = MenuState(
            title_lines=list(title_lines),
            top_items=list(top_items),
            settings_fields=list(settings_fields or []),
        )
        self._settings = settings

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Static(id="overlay-box"):
            for line in self._menu_state.title_lines:
                yield Label(line, classes="overlay-title")
            yield Static(id="menu-items")
            yield Label("↑/↓ move  Enter select  Esc back", classes="overlay-hint")

    def on_mount(self) -> None:
        self._refresh_menu()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_menu(self) -> None:
        """Re-render the menu item list from current MenuState."""
        container = self.query_one("#menu-items", Static)
        items = self._menu_state.items()
        cursor = self._menu_state.cursor
        lines = []
        for i, (label, _action) in enumerate(items):
            prefix = "▶ " if i == cursor else "  "
            cls = "overlay-item-selected" if i == cursor else "overlay-item"
            lines.append(f"[{cls}]{prefix}{label}[/{cls}]")
        container.update("\n".join(lines))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_move_up(self) -> None:
        self._menu_state.move(-1)
        self._refresh_menu()

    def action_move_down(self) -> None:
        self._menu_state.move(1)
        self._refresh_menu()

    def action_select(self) -> None:
        result = self._menu_state.select(self._settings)
        if result == "settings":
            self._refresh_menu()
        else:
            self.dismiss(result)

    def action_back_or_close(self) -> None:
        if self._menu_state.screen == "settings":
            self._menu_state.back()
            self._refresh_menu()
        else:
            self.dismiss("resume")
