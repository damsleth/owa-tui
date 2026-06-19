"""fetch.py — async data-fetch layer for the cal screen.

All blocking owa-tools calls are dispatched via ``asyncio.to_thread`` so the
Textual event loop is never stalled.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

PAGE_SIZE = 50

_SELECT_FIELDS = (
    "Id,Subject,Start,End,Location,Categories,ShowAs,IsAllDay,"
    "OriginalStartTimeZone,OriginalEndTimeZone,Organizer,Attendees,"
    "BodyPreview,ResponseStatus,IsOrganizer"
)


# ---------------------------------------------------------------------------
# Date range helpers (ported verbatim from owa_cal.tui)
# ---------------------------------------------------------------------------


def _today_range() -> tuple[str, str]:
    """Return (from_date, to_date) strings for today only."""
    today = date.today()
    return today.strftime("%Y-%m-%dT00:00:00"), today.strftime("%Y-%m-%dT23:59:59")


def _week_range() -> tuple[str, str]:
    """Return (from_date, to_date) for the current ISO week (Mon–Sun)."""
    from owa_cal.dates import current_iso_week, iso_week_range  # type: ignore[import]

    week, year = current_iso_week()
    from_str, to_str = iso_week_range(week, year)
    return f"{from_str}T00:00:00", f"{to_str}T23:59:59"


def _month_range() -> tuple[str, str]:
    """Return (from_date, to_date) for the current calendar month."""
    today = date.today()
    first = today.replace(day=1)
    # Last day: first day of next month minus one day
    if today.month == 12:
        last = today.replace(month=12, day=31)
    else:
        last = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return first.strftime("%Y-%m-%dT00:00:00"), last.strftime("%Y-%m-%dT23:59:59")


def _resolve_range(day_range: str) -> tuple[str, str]:
    """Resolve a ``day_range`` string to an (from_dt, to_dt) pair."""
    if day_range == "week":
        return _week_range()
    if day_range == "month":
        return _month_range()
    return _today_range()  # default / 'today' / unknown


# ---------------------------------------------------------------------------
# Search / filter helpers
# ---------------------------------------------------------------------------


def _matches_search(event: dict[str, Any], search: str) -> bool:
    """Return True if *event* matches *search* (case-insensitive)."""
    needle = search.lower()
    subject: str = event.get("subject") or ""
    if needle in subject.lower():
        return True
    for att in event.get("attendees") or []:
        if isinstance(att, dict):
            haystack = f"{att.get('name', '')} {att.get('address', '')}".lower()
        else:
            haystack = str(att).lower()
        if needle in haystack:
            return True
    return False


def _is_declined(event: dict[str, Any]) -> bool:
    """Return True if this event should be filtered out as a 'declined' entry."""
    show_as = (event.get("showAs") or "").lower()
    categories = event.get("categories") or []
    return show_as == "free" and not categories


# ---------------------------------------------------------------------------
# Public fetch function
# ---------------------------------------------------------------------------


async def fetch_events(
    access_token: str,
    api_base: str,
    day_range: str,
    show_declined: str,
    search: str = "",
    debug: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch calendar events.

    Returns ``(events, None)`` on success or ``([], error_str)`` on any failure.
    Never raises.
    """
    try:
        from owa_cal.api import OwaError, api_get, build_query  # type: ignore[import]
        from owa_cal.events import normalize_events_detail  # type: ignore[import]

        from_dt, to_dt = _resolve_range(day_range)

        q = build_query(
            {
                "startDateTime": from_dt,
                "endDateTime": to_dt,
                "$top": PAGE_SIZE,
                "$orderby": "Start/DateTime",
                "$select": _SELECT_FIELDS,
            }
        )
        endpoint = f"me/calendarView?{q}"

        def _call() -> Any:
            return api_get(api_base, endpoint, access_token, debug=debug)

        raw = await asyncio.to_thread(_call)

        if raw is None:
            return [], "fetch failed"

        events: list[dict[str, Any]] = normalize_events_detail(raw)

        # Filter declined
        if show_declined == "no":
            events = [e for e in events if not _is_declined(e)]

        # Client-side search
        if search:
            events = [e for e in events if _matches_search(e, search)]

        return events, None

    except Exception as exc:  # noqa: BLE001
        from owa_cal.api import OwaError  # type: ignore[import]

        if isinstance(exc, OwaError):
            return [], f"error: {exc}"
        return [], f"unexpected error: {exc}"


# ---------------------------------------------------------------------------
# Title helper
# ---------------------------------------------------------------------------


def range_title(day_range: str) -> str:
    """Return the header title string for *day_range*."""
    from_dt, to_dt = _resolve_range(day_range)
    from_date = from_dt[:10]
    to_date = to_dt[:10]
    if from_date == to_date:
        return f"owa-cal  {from_date}"
    return f"owa-cal  {from_date} – {to_date}"
