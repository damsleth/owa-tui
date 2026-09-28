"""Unit tests for the shared OwaListScreen keybinding table."""

from __future__ import annotations

from owa_tui.screens.base.keys import LIST_BINDINGS


def _action_for(key: str, bindings=LIST_BINDINGS) -> str | None:
    for b in bindings:
        if key in b.key.split(","):
            return b.action
    return None


def test_navigation_keys_present() -> None:
    assert _action_for("j") == "move_down"
    assert _action_for("k") == "move_up"
    assert _action_for("g") == "go_top"
    assert _action_for("G") == "go_bottom"


def test_open_and_back_keys() -> None:
    # vim + arrow aliases both map to the same actions
    assert _action_for("enter") == "open_item"
    # Tab switches panes; hjkl/arrows stay inside the focused pane.
    assert _action_for("tab") == _action_for("shift+tab") == "focus_pane"
    for key in ("h", "l", "left", "right"):
        assert _action_for(key) is None


def test_trees_keep_lf_style_folder_keys() -> None:
    from owa_tui.screens.base.keys import TREE_NAV_BINDINGS

    assert _action_for("l", TREE_NAV_BINDINGS) == _action_for("right", TREE_NAV_BINDINGS) == "open_item"
    assert _action_for("h", TREE_NAV_BINDINGS) == _action_for("left", TREE_NAV_BINDINGS) == "close_detail"


def test_universal_actions() -> None:
    assert _action_for("r") == "refresh"
    assert _action_for("/") == "search"
    assert _action_for("escape") == "open_menu"
    assert _action_for("q") == "quit"


def test_no_duplicate_key_action_pairs() -> None:
    pairs = [(b.key, b.action) for b in LIST_BINDINGS]
    assert len(pairs) == len(set(pairs))
