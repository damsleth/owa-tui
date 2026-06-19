"""Shared widget kit for owa-tui.

The genuinely shared widgets. Tool screens currently roll their own list and
detail widgets; if a reusable ListBrowser/DetailPane is wanted for v2, rebuild
from the spec in plan 01 §5a/§5b.
"""

from owa_tui.widgets.menu_state import MenuState
from owa_tui.widgets.settings_overlay import SettingsOverlay
from owa_tui.widgets.status_bar import StatusBar

__all__ = ["MenuState", "SettingsOverlay", "StatusBar"]
