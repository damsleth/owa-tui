"""Unit tests for the adapter layer (no live network calls)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

# ---------------------------------------------------------------------------
# fetch_token
# ---------------------------------------------------------------------------


def test_fetch_token_success(monkeypatch: Any) -> None:
    """fetch_token returns (token_info, None) on success."""
    fake_token = {"access_token": "tok123", "expires_in": 3600}

    with patch("owa_core.auth.get_token_for_config", return_value=fake_token):
        from owa_tui.adapter import fetch_token

        result, err = asyncio.run(fetch_token({"tenant": "x"}, tool_name="cal", audience="graph"))
    assert err is None
    assert result == fake_token


def test_fetch_token_none_return(monkeypatch: Any) -> None:
    """fetch_token returns (None, error_str) when get_token_for_config returns None."""
    with patch("owa_core.auth.get_token_for_config", return_value=None):
        from owa_tui.adapter import fetch_token

        result, err = asyncio.run(fetch_token({}, tool_name="cal", audience="graph"))
    assert result is None
    assert err is not None
    assert "None" in err or "auth failed" in err


# ---------------------------------------------------------------------------
# fetch_cal_events
# ---------------------------------------------------------------------------


def test_fetch_cal_events_success(monkeypatch: Any) -> None:
    """fetch_cal_events returns (events, None) when API succeeds."""
    fake_raw = [{"id": "e1", "subject": "Standup"}]
    fake_normalized = [{"id": "e1", "subject": "Standup", "normalized": True}]

    with (
        patch("owa_cal.api.api_get", return_value=fake_raw),
        patch("owa_cal.events.normalize_events", return_value=fake_normalized),
    ):
        from owa_tui.adapter import fetch_cal_events

        events, err = asyncio.run(fetch_cal_events("token", "https://graph.microsoft.com/v1.0"))
    assert err is None
    assert events == fake_normalized


def test_fetch_cal_events_api_returns_none(monkeypatch: Any) -> None:
    """fetch_cal_events returns ([], error) when API returns None."""
    with patch("owa_cal.api.api_get", return_value=None):
        from owa_tui.adapter import fetch_cal_events

        events, err = asyncio.run(fetch_cal_events("token", "https://graph.microsoft.com/v1.0"))
    assert events == []
    assert err is not None


def test_fetch_cal_events_api_raises(monkeypatch: Any) -> None:
    """fetch_cal_events returns ([], error) on exception."""
    with patch("owa_cal.api.api_get", side_effect=RuntimeError("network error")):
        from owa_tui.adapter import fetch_cal_events

        events, err = asyncio.run(fetch_cal_events("token", "https://graph.microsoft.com/v1.0"))
    assert events == []
    assert "network error" in str(err)


def test_fetch_cal_events_with_search(monkeypatch: Any) -> None:
    """fetch_cal_events passes search param when provided."""
    calls: list[dict] = []

    def fake_api_get(api_base: str, path: str, token: str, params: dict, **kw: Any) -> list:
        calls.append({"params": params})
        return []

    with (
        patch("owa_cal.api.api_get", side_effect=fake_api_get),
        patch("owa_cal.events.normalize_events", return_value=[]),
    ):
        from owa_tui.adapter import fetch_cal_events

        asyncio.run(fetch_cal_events("token", "base", search="team meeting"))

    assert len(calls) == 1
    assert calls[0]["params"].get("search") == "team meeting"


# ---------------------------------------------------------------------------
# fetch_mail_messages
# ---------------------------------------------------------------------------


def test_fetch_mail_messages_success(monkeypatch: Any) -> None:
    """fetch_mail_messages returns (messages, None) on success."""
    fake_raw = [{"id": "m1", "subject": "Hello"}]
    fake_normalized = [{"id": "m1", "subject": "Hello", "from": "user@example.com"}]

    with (
        patch("owa_mail.api.api_get", return_value=fake_raw),
        patch("owa_mail.messages.normalize_messages", return_value=fake_normalized),
        patch("owa_mail.messages.build_list_query", return_value="me/messages?$top=50"),
    ):
        from owa_tui.adapter import fetch_mail_messages

        messages, err = asyncio.run(
            fetch_mail_messages("token", "https://graph.microsoft.com/v1.0")
        )
    assert err is None
    assert messages == fake_normalized


def test_fetch_mail_messages_api_returns_none(monkeypatch: Any) -> None:
    """fetch_mail_messages returns ([], error) when API returns None."""
    with (
        patch("owa_mail.api.api_get", return_value=None),
        patch("owa_mail.messages.build_list_query", return_value="me/messages"),
    ):
        from owa_tui.adapter import fetch_mail_messages

        messages, err = asyncio.run(
            fetch_mail_messages("token", "https://graph.microsoft.com/v1.0")
        )
    assert messages == []
    assert err is not None


def test_fetch_mail_messages_raises(monkeypatch: Any) -> None:
    """fetch_mail_messages returns ([], error) on exception."""
    with (
        patch("owa_mail.api.api_get", side_effect=ConnectionError("timeout")),
        patch("owa_mail.messages.build_list_query", return_value="me/messages"),
    ):
        from owa_tui.adapter import fetch_mail_messages

        messages, err = asyncio.run(
            fetch_mail_messages("token", "https://graph.microsoft.com/v1.0")
        )
    assert messages == []
    assert "timeout" in str(err)


# ---------------------------------------------------------------------------
# fetch_graph_request
# ---------------------------------------------------------------------------


def test_fetch_graph_request_success(monkeypatch: Any) -> None:
    """fetch_graph_request returns (data, None) on success."""
    fake_data = {"value": [{"id": "user1"}]}

    with patch("owa_graph.api.api_request", return_value=fake_data):
        from owa_tui.adapter import fetch_graph_request

        data, err = asyncio.run(
            fetch_graph_request("token", "https://graph.microsoft.com/v1.0", "me/people")
        )
    assert err is None
    assert data == fake_data


def test_fetch_graph_request_raises(monkeypatch: Any) -> None:
    """fetch_graph_request returns (None, error) on exception."""
    with patch("owa_graph.api.api_request", side_effect=ValueError("bad request")):
        from owa_tui.adapter import fetch_graph_request

        data, err = asyncio.run(
            fetch_graph_request("token", "https://graph.microsoft.com/v1.0", "me/people")
        )
    assert data is None
    assert "bad request" in str(err)


# ---------------------------------------------------------------------------
# Screens registry
# ---------------------------------------------------------------------------


def test_screen_registry_register_and_lookup() -> None:
    """register_screen and get_screen_class work correctly."""
    from owa_tui.screens import get_screen_class, register_screen

    class FakeScreen:
        pass

    register_screen("_test_tool", "Test Tool", FakeScreen)
    assert get_screen_class("_test_tool") is FakeScreen


def test_screen_registry_unknown_key_returns_none() -> None:
    """get_screen_class returns None for an unknown key."""
    from owa_tui.screens import get_screen_class

    assert get_screen_class("__nonexistent_key__") is None


def test_registered_tools_includes_registered() -> None:
    """registered_tools() includes tools added via register_screen."""
    from owa_tui.screens import register_screen, registered_tools

    class FakeScreen2:
        pass

    register_screen("_test_tool2", "Test Tool 2", FakeScreen2)
    tools = registered_tools()
    assert any(k == "_test_tool2" for k, _ in tools)
