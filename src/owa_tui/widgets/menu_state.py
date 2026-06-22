"""MenuState: pure-Python dataclass driving ``SettingsOverlay`` navigation.

This is the direct successor to ``owa_core.tui_kit.menu.Menu``.  The curses
render method has been removed; navigation and selection logic is preserved.

No Textual imports — this module is fully unit-testable without a running App.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MenuState:
    """Two-level menu model (top screen → settings screen).

    Parameters
    ----------
    title_lines:
        Header lines shown at the top of the overlay box.
    top_items:
        ``[(label, action_str), ...]`` for the top-level menu.
    settings_fields:
        ``[(field_name, display_label), ...]`` for the settings sub-menu.
        Each entry maps one attribute on the settings dataclass.
    screen:
        Current view: ``'top'`` or ``'settings'``.
    cursor:
        Zero-based cursor position within the current item list.
    """

    title_lines: list[str]
    top_items: list[tuple[str, str]]
    settings_fields: list[tuple[str, str]] = field(default_factory=list)
    screen: str = "top"
    cursor: int = 0

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def items(self) -> list[tuple[str, str]]:
        """Return the item list for the current screen."""
        if self.screen == "settings":
            return self.settings_fields
        return self.top_items

    def move(self, delta: int) -> None:
        """Move cursor by *delta* rows, clamping to the valid range."""
        count = len(self.items())
        if count == 0:
            return
        self.cursor = max(0, min(self.cursor + delta, count - 1))

    def back(self) -> None:
        """Return from settings sub-menu to the top screen."""
        if self.screen == "settings":
            self.screen = "top"
            self.cursor = 0

    def open_settings(self) -> None:
        """Enter the settings sub-menu."""
        self.screen = "settings"
        self.cursor = 0

    def reset(self) -> None:
        """Reset to the top screen with the cursor at position 0."""
        self.screen = "top"
        self.cursor = 0
