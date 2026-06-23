"""Unit tests for the adapter layer (no live network calls)."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from unittest.mock import patch

import pytest

# CI-hostile: needs a logged-in owa-piggy broker. Off unless OWA_TUI_LIVE_TESTS=1.
#   OWA_TUI_LIVE_TESTS=1 .venv/bin/python -m pytest src/tests/adapter/ -q
live_only = pytest.mark.skipif(
    os.environ.get("OWA_TUI_LIVE_TESTS") != "1",
    reason="set OWA_TUI_LIVE_TESTS=1 to run live broker smoke",
)

# ---------------------------------------------------------------------------
# access_token_for — the only live function in the adapter
# ---------------------------------------------------------------------------


def test_access_token_for_fixture_mode_returns_dummy(monkeypatch) -> None:
    """When OWA_TUI_FIXTURES is set, a dummy token is returned without minting."""
    monkeypatch.setenv("OWA_TUI_FIXTURES", "/tmp/whatever")
    from owa_tui import fixtures
    from owa_tui.adapter import access_token_for

    assert access_token_for({}, tool_name="owa-cal", audience="outlook") == fixtures.TOKEN


def test_access_token_for_dataclass_shape() -> None:
    """A BrokerToken-like dataclass is read via getattr, not .get()."""

    @dataclass(frozen=True)
    class BrokerToken:
        access_token: str

    with patch("owa_core.auth.get_token_for_config", return_value=BrokerToken("tok-dc")):
        from owa_tui.adapter import access_token_for

        assert access_token_for({}, tool_name="t", audience="graph") == "tok-dc"


def test_access_token_for_dict_and_str_shapes() -> None:
    from owa_tui.adapter import access_token_for

    with patch("owa_core.auth.get_token_for_config", return_value={"access_token": "tok-d"}):
        assert access_token_for({}, tool_name="t", audience="graph") == "tok-d"
    with patch("owa_core.auth.get_token_for_config", return_value="tok-s"):
        assert access_token_for({}, tool_name="t", audience="graph") == "tok-s"


def test_access_token_for_none_and_exception_return_empty() -> None:
    from owa_tui.adapter import access_token_for

    with patch("owa_core.auth.get_token_for_config", return_value=None):
        assert access_token_for({}, tool_name="t", audience="graph") == ""
    with patch("owa_core.auth.get_token_for_config", side_effect=RuntimeError("boom")):
        assert access_token_for({}, tool_name="t", audience="graph") == ""


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


# ---------------------------------------------------------------------------
# current_identity / _upn_from_jwt — header top row (best-effort, never raises)
# ---------------------------------------------------------------------------


def _fake_jwt(claims: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{body}.sig"


def test_upn_from_jwt_reads_claims() -> None:
    from owa_tui.adapter import _upn_from_jwt

    assert _upn_from_jwt(_fake_jwt({"upn": "a@b.com"})) == "a@b.com"
    # falls back through the claim list
    assert _upn_from_jwt(_fake_jwt({"preferred_username": "p@b.com"})) == "p@b.com"


def test_upn_from_jwt_handles_garbage() -> None:
    from owa_tui.adapter import _upn_from_jwt

    assert _upn_from_jwt("") is None
    assert _upn_from_jwt("not-a-jwt") is None
    assert _upn_from_jwt("fixture-token") is None  # dummy token has no claims


def test_current_identity_combines_profile_and_upn() -> None:
    from owa_tui.adapter import current_identity

    @dataclass
    class _Profile:
        alias: str
        default: bool

    profiles = [_Profile("work", False), _Profile("crayon", True)]
    with (
        patch("owa_core.auth.get_profiles", return_value=profiles),
        patch(
            "owa_tui.adapter.access_token_for",
            return_value=_fake_jwt({"upn": "me@crayon.no"}),
        ),
    ):
        assert current_identity({}) == ("crayon", "me@crayon.no")


def test_current_identity_never_raises_on_failure() -> None:
    from owa_tui.adapter import current_identity

    with (
        patch("owa_core.auth.get_profiles", side_effect=RuntimeError("broker down")),
        patch("owa_tui.adapter.access_token_for", side_effect=RuntimeError("no token")),
    ):
        assert current_identity({}) == (None, None)


# ---------------------------------------------------------------------------
# Live broker smoke (opt-in) — mints a real token via owa-piggy
# ---------------------------------------------------------------------------


@live_only
def test_live_access_token_is_usable_jwt(monkeypatch) -> None:
    """Real broker mint returns a JWT we can decode a UPN from."""
    monkeypatch.delenv("OWA_TUI_FIXTURES", raising=False)
    from owa_tui.adapter import _upn_from_jwt, access_token_for

    token = access_token_for({}, tool_name="owa-tui", audience="graph")
    assert token and token.count(".") >= 2, "expected a JWT from the live broker"
    assert _upn_from_jwt(token), "live token has no UPN/preferred_username claim"
