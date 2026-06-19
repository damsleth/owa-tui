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
    # --- open / close detail pane -----------------------------------------
    Binding("enter", "open_item", "Open"),
    Binding("l", "open_item", "Open", show=False),
    Binding("right", "open_item", "Open", show=False),
    Binding("h", "close_detail", "Back", show=False),
    Binding("left", "close_detail", "Back", show=False),
    # --- tab focus toggle -------------------------------------------------
    Binding("tab", "focus_pane", "Focus pane", show=False),
    # --- universal actions ------------------------------------------------
    Binding("r", "refresh", "Refresh"),
    Binding("/", "search", "Search"),
    Binding("o", "open_browser", "Browser", show=False),
    Binding("escape", "open_menu", "Menu"),
    Binding("q", "quit", "Quit"),
]
