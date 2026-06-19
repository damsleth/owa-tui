"""Unit tests for the adapter layer (no live network calls)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

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
