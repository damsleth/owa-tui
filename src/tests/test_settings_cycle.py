"""Tests for the shared settings-cycle stepper."""

from __future__ import annotations

from owa_tui.settings_cycle import cycle_value


def test_steps_forward_and_wraps() -> None:
    assert cycle_value("a", ("a", "b", "c"), 1) == "b"
    assert cycle_value("c", ("a", "b", "c"), 1) == "a"  # wraps


def test_steps_backward_and_wraps() -> None:
    assert cycle_value("b", ("a", "b", "c"), -1) == "a"
    assert cycle_value("a", ("a", "b", "c"), -1) == "c"  # wraps


def test_missing_current_resets_to_first() -> None:
    assert cycle_value("z", ("a", "b", "c"), 1) == "a"
    assert cycle_value(None, (40, 50, 60), -1) == 40


def test_int_sequence() -> None:
    assert cycle_value(40, (40, 50, 60), 1) == 50
    assert cycle_value(60, (40, 50, 60), 1) == 40


def test_bool_toggle() -> None:
    assert cycle_value(False, (False, True), 1) is True
    assert cycle_value(True, (False, True), 1) is False
    assert cycle_value(True, (False, True), -1) is False  # symmetric for len 2


def test_single_element_is_stable() -> None:
    assert cycle_value("only", ("only",), 1) == "only"
