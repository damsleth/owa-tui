"""Shared widget kit for owa-tui.

All reusable Textual widgets live here. Tool-specific subclasses live under
their respective tool package (e.g. ``owa_tui.cal``, ``owa_tui.mail``).
"""

from owa_tui.widgets.detail_pane import DetailPane
from owa_tui.widgets.list_browser import BackPressed, ItemDrilled, ItemSelected, ListBrowser
from owa_tui.widgets.menu_state import MenuState
from owa_tui.widgets.settings_overlay import SettingsOverlay
from owa_tui.widgets.status_bar import StatusBar

__all__ = [
    "BackPressed",
    "DetailPane",
    "ItemDrilled",
    "ItemSelected",
    "ListBrowser",
    "MenuState",
    "SettingsOverlay",
    "StatusBar",
]
