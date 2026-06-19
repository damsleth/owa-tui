"""Unit tests for the shared OwaListScreen keybinding table."""

from __future__ import annotations

from owa_tui.screens.base.keys import LIST_BINDINGS


def _action_for(key: str) -> str | None:
    for b in LIST_BINDINGS:
        if b.key == key:
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
    assert _action_for("l") == "open_item"
    assert _action_for("h") == "close_detail"


def test_universal_actions() -> None:
    assert _action_for("r") == "refresh"
    assert _action_for("/") == "search"
    assert _action_for("escape") == "open_menu"
    assert _action_for("q") == "quit"


def test_no_duplicate_key_action_pairs() -> None:
    pairs = [(b.key, b.action) for b in LIST_BINDINGS]
    assert len(pairs) == len(set(pairs))
