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
        Binding("right", "cycle_fwd", "Change", show=False),
        Binding("l", "cycle_fwd", "Change", show=False),
        Binding("space", "cycle_fwd", "Change", show=False),
        Binding("left", "cycle_back", "Change", show=False),
        Binding("h", "cycle_back", "Change", show=False),
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
        cycle_fn: Any = None,
        on_change: Any = None,
    ) -> None:
        super().__init__()
        self._menu_state = MenuState(
            title_lines=list(title_lines),
            top_items=list(top_items),
            settings_fields=list(settings_fields or []),
        )
        self._settings = settings
        # cycle_fn(settings, field, direction) -> new settings.  Falls back to a
        # plain bool toggle when not supplied.
        self._cycle_fn = cycle_fn
        # on_change(field, new_settings) — called live after every cycle so the
        # parent screen can apply + persist + re-render without the menu closing.
        self._on_change = on_change

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Static(id="overlay-box"):
            for line in self._menu_state.title_lines:
                yield Label(line, classes="overlay-title")
            yield Static(id="menu-items")
            yield Label(
                "↑/↓ move  ←/→ change  Enter select  Esc back",
                classes="overlay-hint",
            )

    def on_mount(self) -> None:
        self._refresh_menu()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_action_field(field: str) -> bool:
        """A settings_fields entry whose name starts with ``_`` is a plain
        action (e.g. ``_reset``) — no value, dismisses on Enter rather than
        cycling."""
        return field.startswith("_")

    def _field_line(self, field: str, label: str) -> str:
        """Render one settings-screen row as ``label: value``.

        Action fields and screens without a live settings object fall back to
        the bare label.
        """
        if self._menu_state.screen != "settings" or self._is_action_field(field):
            return label
        if self._settings is not None and hasattr(self._settings, field):
            return f"{label}: {getattr(self._settings, field)}"
        return label

    def _refresh_menu(self) -> None:
        """Re-render the menu item list from current MenuState."""
        container = self.query_one("#menu-items", Static)
        items = self._menu_state.items()
        cursor = self._menu_state.cursor
        on_settings = self._menu_state.screen == "settings"
        lines = []
        for i, (first, second) in enumerate(items):
            prefix = "▶ " if i == cursor else "  "
            cls = "overlay-item-selected" if i == cursor else "overlay-item"
            # top screen: items are (label, action) → show label.
            # settings screen: items are (field_name, display_label) → show value.
            text = self._field_line(first, second) if on_settings else first
            lines.append(f"[{cls}]{prefix}{text}[/{cls}]")
        container.update("\n".join(lines))

    def _cycle_current(self, direction: int) -> None:
        """Advance the highlighted settings field by *direction* (±1), in place."""
        if self._menu_state.screen != "settings":
            return
        items = self._menu_state.items()
        if not items:
            return
        idx = max(0, min(self._menu_state.cursor, len(items) - 1))
        field, _label = items[idx]
        if self._is_action_field(field):
            return
        if self._cycle_fn is not None:
            self._settings = self._cycle_fn(self._settings, field, direction)
        elif self._settings is not None and isinstance(
            getattr(self._settings, field, None), bool
        ):
            # No cycle_fn supplied — bare bool toggle (direction is irrelevant).
            setattr(self._settings, field, not getattr(self._settings, field))
        self._refresh_menu()
        if self._on_change is not None:
            self._on_change(field, self._settings)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_move_up(self) -> None:
        self._menu_state.move(-1)
        self._refresh_menu()

    def action_move_down(self) -> None:
        self._menu_state.move(1)
        self._refresh_menu()

    def action_cycle_fwd(self) -> None:
        self._cycle_current(1)

    def action_cycle_back(self) -> None:
        self._cycle_current(-1)

    def action_select(self) -> None:
        # On the settings screen, Enter cycles the field in place (action items
        # dismiss with their stripped action string) — it never closes the menu.
        if self._menu_state.screen == "settings":
            items = self._menu_state.items()
            if items:
                idx = max(0, min(self._menu_state.cursor, len(items) - 1))
                field, _label = items[idx]
                if self._is_action_field(field):
                    self.dismiss(field.lstrip("_"))
                    return
            self._cycle_current(1)
            return
        # Top screen: open the settings sub-menu or dismiss with the action.
        first, action = self._menu_state.top_items[self._menu_state.cursor]
        if action == "settings":
            self._menu_state.open_settings()
            self._refresh_menu()
        else:
            self.dismiss(action)

    def action_back_or_close(self) -> None:
        if self._menu_state.screen == "settings":
            self._menu_state.back()
            self._refresh_menu()
        else:
            self.dismiss("resume")
