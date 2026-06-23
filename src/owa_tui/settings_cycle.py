"""Shared settings-cycle stepper.

Every screen's settings model had its own copy of the same "advance a value
through an allowed sequence, wrapping, falling back to the first on a miss"
logic (mail/people/cal sequences + graph's split_ratio and bool toggles).
This is that one stepper, used by all of them.
"""

from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def cycle_value(current: object, allowed: Sequence[T], direction: int = 1) -> T:
    """Return the value after *current* in *allowed*, wrapping by *direction* (±1).

    Falls back to the first allowed value when *current* is absent (or *allowed*
    has a single element). Comparison is by equality, so it works for str, int,
    or bool sequences alike. *allowed* must be non-empty.
    """
    seq = list(allowed)
    try:
        idx = seq.index(current)  # type: ignore[arg-type]
    except ValueError:
        return seq[0]
    return seq[(idx + direction) % len(seq)]


def _demo() -> None:
    # wraps forward and back
    assert cycle_value("a", ("a", "b", "c"), 1) == "b"
    assert cycle_value("c", ("a", "b", "c"), 1) == "a"
    assert cycle_value("a", ("a", "b", "c"), -1) == "c"
    # missing current -> first
    assert cycle_value("z", ("a", "b", "c"), 1) == "a"
    # ints and bools
    assert cycle_value(40, (40, 50, 60), 1) == 50
    assert cycle_value(True, (False, True), 1) is False
    assert cycle_value(False, (False, True), 1) is True
    print("ok")


if __name__ == "__main__":
    _demo()
