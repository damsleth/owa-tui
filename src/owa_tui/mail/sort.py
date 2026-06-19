"""Sort helpers for the owa-tui mail screen.

Ported from owa_tools/src/owa_mail/tui_sort.py — zero I/O, framework-agnostic.

Public API
----------
sort_messages(messages, sort_by) -> list[dict]
    Returns a new sorted list; input is never mutated.

Supported sort_by values (frozenset _SORT_KEYS):
    date_desc    — newest first by received; missing dates sort last
    date_asc     — oldest first by received; missing dates sort last
    sender       — A-Z by from casefold; missing last
    subject      — A-Z by subject casefold; missing last
    unread_first — unread (is_read=False/None) group 0, read group 1;
                   newest-first within each group via _Desc wrapper
"""

from __future__ import annotations

_SORT_KEYS: frozenset[str] = frozenset(
    ["date_desc", "date_asc", "sender", "subject", "unread_first"]
)

_MISSING_HIGH = "\xff" * 32  # sorts last in ascending string comparisons


class _Desc:
    """Wraps a string value so that comparison order is reversed.

    Used to sort newest-first within each unread/read group without
    reversing the outer grouping sort.
    """

    __slots__ = ("_v",)

    def __init__(self, value: str) -> None:
        self._v = value

    def __lt__(self, other: "_Desc") -> bool:
        return self._v > other._v

    def __le__(self, other: "_Desc") -> bool:
        return self._v >= other._v

    def __gt__(self, other: "_Desc") -> bool:
        return self._v < other._v

    def __ge__(self, other: "_Desc") -> bool:
        return self._v <= other._v

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Desc):
            return self._v == other._v
        return NotImplemented


def _key_date_desc(msg: dict) -> tuple[int, str]:
    """Newest first; missing received sorts last.

    With ``reverse=True``, missing entries need the SMALLEST key so they
    end up last.  group 0 = has-date (sorted by received desc), group 1 =
    missing (smallest, sorts last after reverse).
    """
    r = msg.get("received") or ""
    if not r:
        # After reverse=True, ("", "") < ("0", ...) → sorts last ✓
        return (0, "")
    return (1, r)


def _key_date_asc(msg: dict) -> tuple[int, str]:
    """Oldest first; missing received sorts last (not first).

    Without reversing: group 0 = has-date, group 1 = missing (sorts last).
    Within group 0, sort ascending by received string.
    """
    r = msg.get("received") or ""
    if not r:
        return (1, "")
    return (0, r)


def _key_sender(msg: dict) -> str:
    """A-Z by from casefold; missing last."""
    v = msg.get("from") or ""
    return v.casefold() if v else _MISSING_HIGH


def _key_subject(msg: dict) -> str:
    """A-Z by subject casefold; missing last."""
    v = msg.get("subject") or ""
    return v.casefold() if v else _MISSING_HIGH


def _key_unread_first(msg: dict) -> tuple[int, "_Desc"]:
    """Unread group 0, read group 1; newest-first within each group."""
    is_read = msg.get("is_read")
    group = 0 if not is_read else 1
    r = msg.get("received") or ""
    return (group, _Desc(r))


def sort_messages(messages: list[dict], sort_by: str) -> list[dict]:
    """Return a new sorted copy of *messages*.

    Unknown *sort_by* values fall back to ``date_desc`` silently.
    """
    if sort_by not in _SORT_KEYS:
        sort_by = "date_desc"

    if sort_by == "date_desc":
        return sorted(messages, key=_key_date_desc, reverse=True)
    if sort_by == "date_asc":
        return sorted(messages, key=_key_date_asc)
    if sort_by == "sender":
        return sorted(messages, key=_key_sender)
    if sort_by == "subject":
        return sorted(messages, key=_key_subject)
    # unread_first
    return sorted(messages, key=_key_unread_first)
