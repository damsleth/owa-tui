"""Unit tests for MenuState — pure Python, no Textual/Pilot needed."""

from __future__ import annotations

from owa_tui.widgets.menu_state import MenuState

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_initial_state() -> None:
    ms = MenuState(
        title_lines=["My Tool"],
        top_items=[("Resume", "resume"), ("Settings", "settings"), ("Quit", "quit")],
        settings_fields=[("show_declined", "Show declined")],
    )
    assert ms.screen == "top"
    assert ms.cursor == 0
    assert ms.title_lines == ["My Tool"]


# ---------------------------------------------------------------------------
# items()
# ---------------------------------------------------------------------------


def test_items_returns_top_items_on_top_screen() -> None:
    ms = MenuState(
        title_lines=["T"],
        top_items=[("A", "a"), ("B", "b")],
        settings_fields=[("x", "X")],
    )
    assert ms.items() == [("A", "a"), ("B", "b")]


def test_items_returns_settings_fields_on_settings_screen() -> None:
    ms = MenuState(
        title_lines=["T"],
        top_items=[("A", "a")],
        settings_fields=[("x", "X"), ("y", "Y")],
    )
    ms.screen = "settings"
    assert ms.items() == [("x", "X"), ("y", "Y")]


# ---------------------------------------------------------------------------
# move()
# ---------------------------------------------------------------------------


def test_move_clamps_at_zero() -> None:
    ms = MenuState(title_lines=[], top_items=[("A", "a"), ("B", "b")])
    ms.cursor = 0
    ms.move(-5)
    assert ms.cursor == 0


def test_move_clamps_at_end() -> None:
    ms = MenuState(title_lines=[], top_items=[("A", "a"), ("B", "b")])
    ms.cursor = 1
    ms.move(10)
    assert ms.cursor == 1


def test_move_wraps_correctly() -> None:
    ms = MenuState(title_lines=[], top_items=[("A", "a"), ("B", "b"), ("C", "c")])
    ms.move(1)
    assert ms.cursor == 1
    ms.move(1)
    assert ms.cursor == 2
    ms.move(1)
    assert ms.cursor == 2  # clamped


def test_move_with_empty_items_does_nothing() -> None:
    ms = MenuState(title_lines=[], top_items=[])
    ms.move(1)
    assert ms.cursor == 0


# ---------------------------------------------------------------------------
# back() / open_settings() / reset()
# ---------------------------------------------------------------------------


def test_open_settings_switches_screen() -> None:
    ms = MenuState(title_lines=[], top_items=[("A", "a")], settings_fields=[("x", "X")])
    ms.open_settings()
    assert ms.screen == "settings"
    assert ms.cursor == 0


def test_back_from_settings_returns_to_top() -> None:
    ms = MenuState(title_lines=[], top_items=[("A", "a")], settings_fields=[("x", "X")])
    ms.open_settings()
    ms.cursor = 1
    ms.back()
    assert ms.screen == "top"
    assert ms.cursor == 0


def test_back_from_top_is_noop() -> None:
    ms = MenuState(title_lines=[], top_items=[("A", "a")])
    ms.cursor = 0
    ms.back()  # should not crash
    assert ms.screen == "top"


def test_reset_returns_to_top_cursor_zero() -> None:
    ms = MenuState(title_lines=[], top_items=[("A", "a")], settings_fields=[("x", "X")])
    ms.open_settings()
    ms.cursor = 1
    ms.reset()
    assert ms.screen == "top"
    assert ms.cursor == 0
