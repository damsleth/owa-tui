"""keys.py — canonical keybinding set shared by all OwaListScreen tools.

The bindings here are the *intersection* of what cal, mail, and people
all provide.  Tool-specific extras (e.g. mail's ``r toggle-read``, cal's
``y respond``) are added by the concrete subclass via its own BINDINGS
class attribute — Textual merges them automatically.

Import:

    from owa_tui.screens.base.keys import LIST_BINDINGS

then in your Screen subclass::

    BINDINGS = LIST_BINDINGS + [
        Binding("r", "my_action", "My action"),
    ]
"""

from __future__ import annotations

from textual.binding import Binding

# Trees (drive, sites) browse lf-style: l/→ into a folder, h/← up one. That is
# navigation inside the list, so they keep these on top of LIST_BINDINGS.
TREE_NAV_BINDINGS: list[Binding] = [
    Binding("l,right", "open_item", "Open", show=False),
    Binding("h,left", "close_detail", "Up", show=False),
]

LIST_BINDINGS: list[Binding] = [
    # --- navigation -------------------------------------------------------
    Binding("j", "move_down", "Down", show=False),
    Binding("down", "move_down", "Down", show=False),
    Binding("k", "move_up", "Up", show=False),
    Binding("up", "move_up", "Up", show=False),
    Binding("d", "page_down", "Page Down", show=False),
    Binding("u", "page_up", "Page Up", show=False),
    Binding("g", "go_top", "Top", show=False),
    Binding("G", "go_bottom", "Bottom", show=False),
    # --- open detail / switch pane ------------------------------------------
    # Tab switches panes; arrows and hjkl stay inside the focused pane.
    Binding("enter", "open_item", "Open"),
    Binding("tab,shift+tab", "focus_pane", "Switch pane", show=False),
    # --- universal actions ------------------------------------------------
    Binding("r", "refresh", "Refresh"),
    Binding("/", "search", "Search"),
    Binding("o", "open_browser", "Browser", show=False),
    Binding("escape", "open_menu", "Menu"),
    Binding("q", "quit", "Quit"),
]
