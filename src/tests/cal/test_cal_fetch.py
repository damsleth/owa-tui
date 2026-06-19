"""Unit tests for fetch_events and date-range helpers.

No network calls — api_get is monkeypatched.
Mirrors TestFetchItems from test_tui.py (curses version).
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOKEN = "fake-token"
_BASE = "https://graph.microsoft.com/v1.0"

_RAW_EVENT: dict = {
    "Id": "evt-001",
    "Subject": "Morning call",
    "Start": {"DateTime": "2026-06-18T09:00:00", "TimeZone": "UTC"},
    "End": {"DateTime": "2026-06-18T09:30:00", "TimeZone": "UTC"},
    "IsAllDay": False,
    "ShowAs": "busy",
    "Categories": [],
    "Location": {"DisplayName": ""},
    "Organizer": {"EmailAddress": {"Name": "Alice", "Address": "alice@x.com"}},
    "Attendees": [
        {
            "EmailAddress": {"Name": "Bob", "Address": "bob@x.com"},
            "Type": "Required",
            "Status": {"Response": "Accepted", "Time": "2026-06-18T08:00:00Z"},
        }
    ],
    "BodyPreview": "Daily sync.",
    "ResponseStatus": {"Response": "Accepted", "Time": "2026-06-18T08:00:00Z"},
    "IsOrganizer": False,
}

_RAW_RESPONSE = {"value": [_RAW_EVENT]}


def _patch_api_get(monkeypatch: pytest.MonkeyPatch, return_value: Any) -> None:
    monkeypatch.setattr(
        "owa_tui.screens.cal.fetch.asyncio.to_thread",
        lambda fn, *a, **kw: asyncio.coroutine(lambda: return_value)(),
    )


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_returns_events_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_events returns (list, None) when api_get succeeds."""

    async def _run() -> tuple:
        import owa_tui.screens.cal.fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.asyncio,
            "to_thread",
            lambda fn, *a, **kw: _async_ret(_RAW_RESPONSE),
        )
        return await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "no")

    events, err = asyncio.run(_run())
    assert err is None
    assert len(events) == 1
    assert events[0]["subject"] == "Morning call"


def test_returns_empty_on_api_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_events returns ([], 'fetch failed') when api_get returns None."""

    async def _run() -> tuple:
        import owa_tui.screens.cal.fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.asyncio,
            "to_thread",
            lambda fn, *a, **kw: _async_ret(None),
        )
        return await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "no")

    events, err = asyncio.run(_run())
    assert events == []
    assert err == "fetch failed"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_does_not_raise_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_events never raises — generic Exception becomes error string."""

    async def _run() -> tuple:
        import owa_tui.screens.cal.fetch as fetch_mod

        async def _boom(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(fetch_mod.asyncio, "to_thread", _boom)
        return await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "no")

    events, err = asyncio.run(_run())
    assert events == []
    assert err is not None
    assert "boom" in err


def test_owa_error_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """OwaError from api_get is caught and returned as error string."""

    async def _run() -> tuple:
        from owa_cal.api import OwaError

        import owa_tui.screens.cal.fetch as fetch_mod

        async def _raise(*a, **kw):
            raise OwaError("auth expired")

        monkeypatch.setattr(fetch_mod.asyncio, "to_thread", _raise)
        return await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "no")

    events, err = asyncio.run(_run())
    assert events == []
    assert err is not None
    assert "auth expired" in err


def test_unexpected_exception_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected Exception is caught and returned as 'unexpected error:' string."""

    async def _run() -> tuple:
        import owa_tui.screens.cal.fetch as fetch_mod

        async def _raise(*a, **kw):
            raise ValueError("unexpected")

        monkeypatch.setattr(fetch_mod.asyncio, "to_thread", _raise)
        return await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "no")

    events, err = asyncio.run(_run())
    assert events == []
    assert "unexpected" in (err or "")


# ---------------------------------------------------------------------------
# Search filter
# ---------------------------------------------------------------------------


def test_search_filter_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search by subject keeps matching events."""

    async def _run() -> tuple:
        import owa_tui.screens.cal.fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.asyncio,
            "to_thread",
            lambda fn, *a, **kw: _async_ret(_RAW_RESPONSE),
        )
        return await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "no", search="morning")

    events, err = asyncio.run(_run())
    assert len(events) == 1


def test_search_filter_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search with no match returns empty list."""

    async def _run() -> tuple:
        import owa_tui.screens.cal.fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.asyncio,
            "to_thread",
            lambda fn, *a, **kw: _async_ret(_RAW_RESPONSE),
        )
        return await fetch_mod.fetch_events(
            _TOKEN, _BASE, "today", "no", search="zzz_no_match"
        )

    events, _ = asyncio.run(_run())
    assert len(events) == 0


def test_search_filter_attendee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search matches attendee name/address (dict shape)."""

    async def _run() -> tuple:
        import owa_tui.screens.cal.fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.asyncio,
            "to_thread",
            lambda fn, *a, **kw: _async_ret(_RAW_RESPONSE),
        )
        # "bob" appears in attendee name
        return await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "no", search="bob")

    events, _ = asyncio.run(_run())
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Show-declined filter
# ---------------------------------------------------------------------------


def test_show_declined_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """show_declined='no' removes events where showAs==free and no categories."""
    free_event = {**_RAW_EVENT, "ShowAs": "Free", "Categories": []}
    raw = {"value": [free_event]}

    async def _run(show_declined: str) -> list:
        import owa_tui.screens.cal.fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.asyncio,
            "to_thread",
            lambda fn, *a, **kw: _async_ret(raw),
        )
        events, _ = await fetch_mod.fetch_events(
            _TOKEN, _BASE, "today", show_declined
        )
        return events

    # With 'no' — declined event removed
    events_no = asyncio.run(_run("no"))
    assert len(events_no) == 0

    # With 'yes' — declined event shown
    events_yes = asyncio.run(_run("yes"))
    assert len(events_yes) == 1


def test_show_declined_yes_shows_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """show_declined='yes' shows all events regardless of showAs."""

    async def _run() -> list:
        import owa_tui.screens.cal.fetch as fetch_mod

        monkeypatch.setattr(
            fetch_mod.asyncio,
            "to_thread",
            lambda fn, *a, **kw: _async_ret(_RAW_RESPONSE),
        )
        events, _ = await fetch_mod.fetch_events(_TOKEN, _BASE, "today", "yes")
        return events

    events = asyncio.run(_run())
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Date range helpers
# ---------------------------------------------------------------------------


def test_today_range() -> None:
    from owa_tui.screens.cal.fetch import _today_range

    from_dt, to_dt = _today_range()
    today = date.today().strftime("%Y-%m-%d")
    assert from_dt.startswith(today)
    assert to_dt.startswith(today)
    assert "00:00:00" in from_dt
    assert "23:59:59" in to_dt


def test_week_range_monday_sunday() -> None:
    from owa_tui.screens.cal.fetch import _week_range

    from_dt, to_dt = _week_range()
    # from should be a Monday (weekday 0)
    from datetime import datetime

    from_date = datetime.fromisoformat(from_dt).date()
    to_date = datetime.fromisoformat(to_dt).date()
    assert from_date.weekday() == 0  # Monday
    assert to_date.weekday() == 6  # Sunday
    assert (to_date - from_date).days == 6


def test_month_range_first_last() -> None:
    from owa_tui.screens.cal.fetch import _month_range

    from_dt, to_dt = _month_range()
    from datetime import datetime

    from_date = datetime.fromisoformat(from_dt).date()
    to_date = datetime.fromisoformat(to_dt).date()
    assert from_date.day == 1
    assert from_date.month == to_date.month or (
        from_date.month == 12 and to_date.month == 12
    )


def test_unknown_day_range_falls_back_to_today() -> None:
    from owa_tui.screens.cal.fetch import _resolve_range, _today_range

    expected = _today_range()
    assert _resolve_range("unknown_xyz") == expected


# ---------------------------------------------------------------------------
# Title helper
# ---------------------------------------------------------------------------


def test_title_single_day() -> None:
    from owa_tui.screens.cal.fetch import range_title

    title = range_title("today")
    assert "owa-cal" in title
    # Single day: no ' – ' separator
    assert " – " not in title


def test_title_multi_day() -> None:
    from owa_tui.screens.cal.fetch import range_title

    title = range_title("week")
    assert " – " in title


def test_title_month() -> None:
    from owa_tui.screens.cal.fetch import range_title

    title = range_title("month")
    assert " – " in title


# ---------------------------------------------------------------------------
# Helper coroutine
# ---------------------------------------------------------------------------


async def _async_ret(value: Any) -> Any:
    return value
