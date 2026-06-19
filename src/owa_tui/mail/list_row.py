"""list_row renderer for the owa-tui mail message list.

Ported from owa_tools/src/owa_mail/tui_layout.py (list_row function only).

Layout: <date> <*!@> <sender ~30%>  <subject fills rest>

Fixed column widths by format:
    iso8601:    10
    ddmm:        5
    ddmm_hhmm:  11
    custom:      10 (default budget)

Marker column (3 chars): unread=*/space, flag=!/space (flag='Flagged'),
attachment=@/space.

Sender gets max(min(int(remaining * 0.30), remaining - sep - 1), 0) cols.
Subject fills the rest; sep = '  ' (2 chars).
Final output hard-truncated to width via a local truncate_ellipsis.
"""

from __future__ import annotations

from owa_tui.mail.dates import format_received

_DATE_WIDTHS: dict[str, int] = {
    "iso8601": 10,
    "ddmm": 5,
    "ddmm_hhmm": 11,
    "custom": 10,
}
_SEP = "  "


def _truncate_ellipsis(s: str, width: int) -> str:
    """Hard-truncate *s* to *width* chars, adding … if truncated."""
    if width <= 0:
        return ""
    if len(s) <= width:
        return s
    if width == 1:
        return "…"
    return s[: width - 1] + "…"


def _pad(s: str, width: int) -> str:
    """Left-justify *s* in a field of *width*, truncating if too long."""
    if width <= 0:
        return ""
    return s[:width].ljust(width)


def list_row(
    msg: dict,
    width: int,
    *,
    date_fmt: str = "iso8601",
    custom_fmt: str = "",
) -> str:
    """Render *msg* as a single list-row string of at most *width* chars.

    Parameters
    ----------
    msg:
        Normalised message dict (from normalize_message / normalize_messages).
    width:
        Terminal/widget width to fit into.
    date_fmt:
        One of ``iso8601``, ``ddmm``, ``ddmm_hhmm``, ``custom``.
    custom_fmt:
        strftime string used when *date_fmt* is ``"custom"``.
    """
    date_width = _DATE_WIDTHS.get(date_fmt, 10)
    date_str = format_received(msg.get("received") or "", date_fmt, custom_fmt)
    date_col = _pad(date_str, date_width)

    unread_mark = " " if msg.get("is_read") else "*"
    flag_mark = "!" if msg.get("flag") == "Flagged" else " "
    att_mark = "@" if msg.get("has_attachments") else " "
    marker_col = f"{unread_mark}{flag_mark}{att_mark}"  # 3 chars

    # Remaining width after date + space + marker + space
    fixed = date_width + 1 + 3 + 1
    remaining = max(0, width - fixed)

    sep_len = len(_SEP)
    sender_width = max(min(int(remaining * 0.30), remaining - sep_len - 1), 0)
    subject_width = max(0, remaining - sender_width - sep_len)

    sender_raw = msg.get("from") or ""
    subject_raw = msg.get("subject") or "(no subject)"

    sender_col = _pad(sender_raw, sender_width)
    subject_col = _pad(subject_raw, subject_width)

    row = f"{date_col} {marker_col} {sender_col}{_SEP}{subject_col}"
    return _truncate_ellipsis(row, width)
