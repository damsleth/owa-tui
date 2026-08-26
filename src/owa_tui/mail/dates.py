"""Date formatters for the owa-tui mail screen.

Ported from owa_tools/src/owa_mail/tui_dates.py — zero I/O, framework-agnostic.

Public API
----------
parse_iso(iso) -> datetime | None
    Parse a Graph ISO 8601 timestamp, tolerating the trailing ``Z``.

format_received(iso, fmt, custom="") -> str
    Format an ISO 8601 received timestamp for display.

validate_custom_format(s) -> bool
    Return True if *s* is a usable strftime format string.
"""

from __future__ import annotations

from datetime import datetime

_SAMPLE = datetime(2000, 1, 2, 3, 4, 5)


def parse_iso(iso: str) -> datetime | None:
    """Parse an ISO 8601 string to datetime; return None on failure.

    Graph stamps its timestamps with a trailing ``Z``, which
    ``datetime.fromisoformat`` only accepts on 3.11+ - on the 3.10 this
    package still supports it raises, and the date renders empty.
    Rewriting it to ``+00:00`` first parses identically on both (3.11 also
    returns a UTC-aware datetime for ``Z``).

    Shared with the calendar agenda: the same Graph timestamps reach both
    screens, so the workaround lives in one place.
    """
    if not iso:
        return None
    text = iso.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def format_received(iso: str, fmt: str, custom: str = "") -> str:
    """Format *iso* timestamp according to *fmt*.

    Parameters
    ----------
    iso:
        ISO 8601 string (may include trailing ``Z`` or ``+HH:MM``).
    fmt:
        One of ``iso8601``, ``ddmm``, ``ddmm_hhmm``, ``custom``.
    custom:
        strftime format string used when *fmt* is ``"custom"``.
        Falls back to ``"%Y-%m-%d"`` if empty.

    Returns empty string on unparseable input or strftime errors.
    """
    dt = parse_iso(iso)
    if dt is None:
        return ""

    if fmt == "iso8601":
        strfmt = "%Y-%m-%d"
    elif fmt == "ddmm":
        strfmt = "%d.%m"
    elif fmt == "ddmm_hhmm":
        strfmt = "%d.%m %H:%M"
    elif fmt == "custom":
        strfmt = custom if custom else "%Y-%m-%d"
    else:
        strfmt = "%Y-%m-%d"

    try:
        return dt.strftime(strfmt)
    except Exception:
        return ""


def validate_custom_format(s: str) -> bool:
    """Return True if *s* is a usable strftime format string.

    Uses a fixed sample datetime (2000-01-02 03:04:05) so the result is
    deterministic.  Returns False for empty/whitespace-only strings,
    and for formats that raise on strftime (e.g. ``%Z`` on a naive
    datetime returns ``""`` → treated as invalid here to match the
    original curses behaviour).
    """
    if not s or not s.strip():
        return False
    try:
        result = _SAMPLE.strftime(s)
        # %Z on a naive datetime returns "" — reject
        if not result:
            return False
        return True
    except Exception:
        return False
