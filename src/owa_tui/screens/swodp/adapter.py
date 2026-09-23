"""adapter.py — the only module that imports ``owa_swodp``.

All calls are blocking; run them from a worker thread. Each one checks the
fixture seam (``OWA_TUI_FIXTURES``) before touching a session, so fixture mode
never launches Edge or talks to ServiceNow.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from owa_tui import fixtures

_OUTLOOK_BASE = "https://outlook.office.com/api/v2.0"

# Fixture stand-in for a captured session; never sent anywhere.
FIXTURE_SESSION = object()


class SwodpAuthError(RuntimeError):
    """Session missing or expired; the message carries the setup hint."""


def capture(instance: str) -> Any:
    """Capture a SWODP session (launches headless Edge; takes seconds)."""
    if fixtures.enabled():
        return FIXTURE_SESSION
    from owa_core.errors import AuthExpiredError  # type: ignore[import]  # noqa: PLC0415
    from owa_swodp import session  # type: ignore[import]  # noqa: PLC0415

    try:
        return session.capture(instance)
    except AuthExpiredError as exc:
        raise _auth_error(exc, instance) from exc


def _auth_error(exc: Exception, instance: str) -> SwodpAuthError:
    hint = getattr(exc, "remediation", None) or f"Run: owa-swodp setup --instance {instance}"
    return SwodpAuthError(f"{exc} — {hint}")


def week(session: Any, monday: date, instance: str) -> list[dict]:
    """Raw cards for the 3-week window around *monday* (filter per week in plan)."""
    if session is FIXTURE_SESSION:
        return fixtures.load("swodp") or []
    from owa_core.errors import AuthExpiredError  # type: ignore[import]  # noqa: PLC0415
    from owa_swodp import service  # type: ignore[import]  # noqa: PLC0415

    try:
        return service.week_cards(session, monday.isoformat())
    except AuthExpiredError as exc:
        raise _auth_error(exc, instance) from exc


def categories(session: Any) -> dict[str, str]:
    """Display name -> raw category value; ``{}`` when the lookup fails."""
    if session is FIXTURE_SESSION:
        # ponytail: fixture-only guess; live mode asks SWODP.
        cards = fixtures.load("swodp") or []
        return {c["category"]: c["category"].lower() for c in cards if not c.get("task.number")}
    from owa_swodp import service  # type: ignore[import]  # noqa: PLC0415

    try:
        return service.categories(session)
    except Exception:  # noqa: BLE001 — no picker is fine; plan falls back to lower()
        return {}


def write(session: Any, monday: date, rows: list[dict]) -> list[dict]:
    """Validate and write *rows*; returns ``results`` (one dict per action)."""
    validate(rows)
    if session is FIXTURE_SESSION:
        return [
            {"taskNumber": r.get("taskNumber") or r["category"],
             "action": "deleted" if r.get("remove") else "updated"}
            for r in rows
        ]
    from owa_swodp import service  # type: ignore[import]  # noqa: PLC0415

    return service.write_week(session, monday.isoformat(), rows)


def validate(rows: list[dict]) -> None:
    """Raise ``UsageError`` (message names the row) unless *rows* fit the contract."""
    from owa_swodp import service  # type: ignore[import]  # noqa: PLC0415

    service.validate_write_rows(rows)


def calendar_events(config: dict[str, Any], profile: str, monday: date) -> list[dict]:
    """Normalized Outlook events for the week, from *profile*'s calendar."""
    from owa_cal.api import api_get  # type: ignore[import]  # noqa: PLC0415
    from owa_cal.events import normalize_events_detail  # type: ignore[import]  # noqa: PLC0415
    from owa_core.query import build_query  # type: ignore[import]

    raw = fixtures.load("swodp_cal")
    if raw is None and not fixtures.enabled():
        from owa_tui.adapter import access_token_for, retrying  # noqa: PLC0415

        cfg = {**config, "owa_piggy_profile": profile}
        token = access_token_for(cfg, tool_name="owa-cal", audience="outlook")
        if not token:
            raise SwodpAuthError(f"no calendar token for profile {profile!r}")
        sunday = monday + timedelta(days=6)
        q = build_query(
            {
                "startDateTime": f"{monday.isoformat()}T00:00:00",
                "endDateTime": f"{sunday.isoformat()}T23:59:59",
                "$top": 250,  # ponytail: one page; a week with >250 events is not a work week
                "$orderby": "Start/DateTime",
                "$select": "Id,Subject,Start,End,Categories,ShowAs,IsAllDay",
            }
        )
        raw = retrying(lambda: api_get(_OUTLOOK_BASE, f"me/calendarView?{q}", token))
    return normalize_events_detail(raw or {})
