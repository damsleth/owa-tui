"""SWODP adapter: fixture seam, auth-error mapping, calendar path. No Edge, no network."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from owa_core.errors import AuthExpiredError, UsageError

from owa_tui.screens.swodp import adapter

FIXTURES = Path(__file__).resolve().parents[3] / "e2e" / "fixtures"
MONDAY = date(2026, 9, 14)
ROW = {"taskNumber": "T1PRJTSK4228809", "days": [1, 0, 0, 0, 0, 0, 0], "description": "x"}


@pytest.fixture
def fixture_mode(monkeypatch):
    monkeypatch.setenv("OWA_TUI_FIXTURES", str(FIXTURES))


def test_fixture_mode_never_touches_a_session(fixture_mode) -> None:
    session = adapter.capture("prod")
    assert session is adapter.FIXTURE_SESSION
    assert len(adapter.week(session, MONDAY, "prod")) == 4
    assert adapter.categories(session) == {"Admin": "admin"}
    results = adapter.write(session, MONDAY, [ROW, {**ROW, "remove": True}])
    assert [r["action"] for r in results] == ["updated", "deleted"]


def test_write_validates_before_anything(fixture_mode) -> None:
    with pytest.raises(UsageError, match="description"):
        adapter.write(adapter.FIXTURE_SESSION, MONDAY, [{**ROW, "description": ""}])


def test_fixture_calendar_is_normalized(fixture_mode) -> None:
    events = adapter.calendar_events({}, "swon", MONDAY)
    assert events[0]["subject"] == "NOCOS triage"
    assert events[0]["categories"] == ["NC NOCOS"]


def test_auth_expired_carries_setup_hint(monkeypatch) -> None:
    monkeypatch.delenv("OWA_TUI_FIXTURES", raising=False)
    err = AuthExpiredError("not authenticated", remediation="Run: owa-swodp setup --instance uat")
    with patch("owa_swodp.session.capture", side_effect=err):
        with pytest.raises(adapter.SwodpAuthError, match="owa-swodp setup --instance uat"):
            adapter.capture("uat")
    with patch("owa_swodp.service.week_cards", side_effect=AuthExpiredError("expired")):
        with pytest.raises(adapter.SwodpAuthError, match="setup --instance prod"):
            adapter.week(object(), MONDAY, "prod")


def test_live_paths_delegate_to_owa_swodp(monkeypatch) -> None:
    monkeypatch.delenv("OWA_TUI_FIXTURES", raising=False)
    s = object()
    with patch("owa_swodp.service.week_cards", return_value=[{"x": 1}]) as wc:
        assert adapter.week(s, MONDAY, "prod") == [{"x": 1}]
    wc.assert_called_once_with(s, "2026-09-14")
    with patch("owa_swodp.service.categories", side_effect=RuntimeError("403")):
        assert adapter.categories(s) == {}
    with patch("owa_swodp.service.write_week", return_value=[{"action": "created"}]) as ww:
        assert adapter.write(s, MONDAY, [ROW]) == [{"action": "created"}]
    ww.assert_called_once_with(s, "2026-09-14", [ROW])


def test_live_calendar_uses_profile_and_outlook_audience(monkeypatch) -> None:
    monkeypatch.delenv("OWA_TUI_FIXTURES", raising=False)
    with (
        patch("owa_tui.adapter.access_token_for", return_value="tok") as tok,
        patch("owa_cal.api.api_get", return_value={"value": []}) as get,
    ):
        assert adapter.calendar_events({"x": 1}, "swon", MONDAY) == []
    assert tok.call_args.args[0]["owa_piggy_profile"] == "swon"
    assert tok.call_args.kwargs == {"tool_name": "owa-cal", "audience": "outlook"}
    assert "endDateTime=2026-09-20T23%3A59%3A59" in get.call_args.args[1]
    with patch("owa_tui.adapter.access_token_for", return_value=""):
        with pytest.raises(adapter.SwodpAuthError, match="swon"):
            adapter.calendar_events({}, "swon", MONDAY)
