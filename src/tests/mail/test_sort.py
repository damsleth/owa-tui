"""Tests for owa_tui.mail.sort — pure sort logic."""

from __future__ import annotations

from owa_tui.mail.sort import _Desc, sort_messages

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _msg(
    id_: str,
    received: str,
    from_: str = "",
    subject: str = "",
    is_read: bool = True,
) -> dict:
    return {
        "id": id_,
        "received": received,
        "from": from_,
        "subject": subject,
        "is_read": is_read,
    }


MSGS = [
    _msg("a", "2026-05-10T09:00:00Z", from_="alice@x.com", subject="Apple", is_read=True),
    _msg("b", "2026-05-12T08:00:00Z", from_="bob@x.com", subject="Banana", is_read=False),
    _msg("c", "2026-05-11T07:00:00Z", from_="carol@x.com", subject="Cherry", is_read=True),
    _msg("d", "2026-05-13T06:00:00Z", from_="dave@x.com", subject="Date", is_read=False),
    _msg("e", "", from_="eve@x.com", subject="Elderberry", is_read=True),  # missing received
]


# ---------------------------------------------------------------------------
# date_desc
# ---------------------------------------------------------------------------


def test_sort_date_desc_newest_first() -> None:
    result = sort_messages(MSGS, "date_desc")
    # d > b > c > a > e(missing)
    received = [m["received"] for m in result]
    non_empty = [r for r in received if r]
    assert non_empty == sorted(non_empty, reverse=True)


def test_sort_date_desc_missing_sorts_last() -> None:
    result = sort_messages(MSGS, "date_desc")
    assert result[-1]["id"] == "e"


def test_sort_date_desc_does_not_mutate() -> None:
    original_ids = [m["id"] for m in MSGS]
    sort_messages(MSGS, "date_desc")
    assert [m["id"] for m in MSGS] == original_ids


# ---------------------------------------------------------------------------
# date_asc
# ---------------------------------------------------------------------------


def test_sort_date_asc_oldest_first() -> None:
    result = sort_messages(MSGS, "date_asc")
    non_empty = [m for m in result if m["received"]]
    received = [m["received"] for m in non_empty]
    assert received == sorted(received)


def test_sort_date_asc_missing_still_sorts_last() -> None:
    result = sort_messages(MSGS, "date_asc")
    assert result[-1]["id"] == "e"


# ---------------------------------------------------------------------------
# sender
# ---------------------------------------------------------------------------


def test_sort_sender_alphabetical() -> None:
    result = sort_messages(MSGS[:4], "sender")
    senders = [m["from"].casefold() for m in result]
    assert senders == sorted(senders)


def test_sort_sender_missing_last() -> None:
    msgs = [
        _msg("x", "2026-01-01T00:00:00Z", from_=""),
        _msg("a", "2026-01-02T00:00:00Z", from_="alice@x.com"),
    ]
    result = sort_messages(msgs, "sender")
    assert result[0]["id"] == "a"
    assert result[-1]["id"] == "x"


# ---------------------------------------------------------------------------
# subject
# ---------------------------------------------------------------------------


def test_sort_subject_alphabetical() -> None:
    result = sort_messages(MSGS[:4], "subject")
    subjects = [m["subject"].casefold() for m in result]
    assert subjects == sorted(subjects)


def test_sort_subject_missing_last() -> None:
    msgs = [
        _msg("x", "2026-01-01T00:00:00Z", subject=""),
        _msg("a", "2026-01-02T00:00:00Z", subject="Alpha"),
    ]
    result = sort_messages(msgs, "subject")
    assert result[0]["id"] == "a"
    assert result[-1]["id"] == "x"


# ---------------------------------------------------------------------------
# unread_first
# ---------------------------------------------------------------------------


def test_sort_unread_first_group() -> None:
    result = sort_messages(MSGS[:4], "unread_first")
    unread = [m for m in result if not m["is_read"]]
    read = [m for m in result if m["is_read"]]
    # All unread come before all read
    assert result[: len(unread)] == unread
    assert result[len(unread) :] == read


def test_sort_unread_first_newest_within_group() -> None:
    unread_msgs = [
        _msg("u1", "2026-05-10T09:00:00Z", is_read=False),
        _msg("u2", "2026-05-12T09:00:00Z", is_read=False),
    ]
    result = sort_messages(unread_msgs, "unread_first")
    # Newest unread first within unread group
    assert result[0]["id"] == "u2"
    assert result[1]["id"] == "u1"


def test_sort_unread_first_none_is_read_treated_as_unread() -> None:
    msgs = [
        {"id": "n", "received": "2026-05-10T09:00:00Z", "from": "", "subject": "", "is_read": None},
        {"id": "r", "received": "2026-05-10T09:00:00Z", "from": "", "subject": "", "is_read": True},
    ]
    result = sort_messages(msgs, "unread_first")
    assert result[0]["id"] == "n"


# ---------------------------------------------------------------------------
# Unknown sort_by falls back to date_desc
# ---------------------------------------------------------------------------


def test_sort_unknown_falls_back_to_date_desc() -> None:
    result = sort_messages(MSGS[:4], "bogus_sort")
    by_date = sort_messages(MSGS[:4], "date_desc")
    assert result == by_date


# ---------------------------------------------------------------------------
# _Desc wrapper
# ---------------------------------------------------------------------------


def test_desc_inverts_comparison() -> None:
    a = _Desc("2026-05-10")
    b = _Desc("2026-05-12")
    # b is "bigger" ISO, so _Desc(b) < _Desc(a)
    assert b < a
    assert a > b


def test_desc_equal() -> None:
    a = _Desc("2026-05-10")
    b = _Desc("2026-05-10")
    assert a == b
