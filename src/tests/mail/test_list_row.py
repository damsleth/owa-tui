"""Tests for owa_tui.mail.list_row — row renderer."""

from __future__ import annotations

from owa_tui.mail.list_row import list_row


def _msg(**kw) -> dict:
    defaults = {
        "id": "m0",
        "received": "2026-05-10T09:00:00Z",
        "from": "alice@example.com",
        "subject": "Test subject",
        "is_read": True,
        "flag": "NotFlagged",
        "has_attachments": False,
    }
    defaults.update(kw)
    return defaults


class TestListRow:
    def test_contains_date_iso8601(self) -> None:
        row = list_row(_msg(), 100, date_fmt="iso8601")
        assert "2026-05-10" in row

    def test_contains_date_ddmm(self) -> None:
        row = list_row(_msg(), 100, date_fmt="ddmm")
        assert "10.05" in row

    def test_contains_date_ddmm_hhmm(self) -> None:
        row = list_row(_msg(), 100, date_fmt="ddmm_hhmm")
        assert "10.05 09:00" in row

    def test_contains_date_custom(self) -> None:
        row = list_row(_msg(), 100, date_fmt="custom", custom_fmt="%Y/%m/%d")
        assert "2026/05/10" in row

    def test_unread_marker_present(self) -> None:
        row = list_row(_msg(is_read=False), 100)
        # Unread marker '*' present
        assert "*" in row

    def test_read_no_unread_marker(self) -> None:
        row = list_row(_msg(is_read=True), 100)
        # The marker position should be ' ', not '*' — verify no '*' in marker position
        # (difficult to pin exact position, but if the msg is read, no * in the marker)
        # We check that the row doesn't start with a '*' at the marker
        # Instead check that the unread marker column has a space
        # Date is 10 chars, then space, then marker at index 11
        assert row[11] == " "  # iso8601 width=10, space, then marker

    def test_flag_marker(self) -> None:
        row = list_row(_msg(flag="Flagged"), 100)
        assert "!" in row

    def test_attachment_marker(self) -> None:
        row = list_row(_msg(has_attachments=True), 100)
        assert "@" in row

    def test_no_attachment_no_at(self) -> None:
        row = list_row(_msg(has_attachments=False), 100)
        # '@' should not appear in the marker area
        assert row[13] == " "  # iso8601: date(10)+sp+marker(3 chars: idx 11,12,13)

    def test_width_truncated(self) -> None:
        row = list_row(_msg(), 30)
        assert len(row) <= 30

    def test_no_subject_fallback(self) -> None:
        row = list_row(_msg(subject=""), 100)
        assert "(no subject)" in row

    def test_sender_in_row(self) -> None:
        row = list_row(_msg(), 120)
        assert "alice" in row

    def test_subject_in_row(self) -> None:
        row = list_row(_msg(), 120)
        assert "Test subject" in row

    def test_zero_width_returns_empty_or_short(self) -> None:
        row = list_row(_msg(), 0)
        assert row == ""

    def test_missing_received_empty_date(self) -> None:
        row = list_row(_msg(received=""), 100)
        # Date portion is blank/padded
        assert row[:10] == " " * 10
