"""Unit tests for the base auth helper (token_for)."""

from __future__ import annotations

from unittest.mock import patch

from owa_tui.screens.base.auth import token_for


def test_token_for_returns_token_on_success() -> None:
    with patch("owa_tui.adapter.access_token_for", return_value="tok-123") as m:
        out = token_for({"k": "v"}, tool_name="owa-mail", audience="outlook")
    assert out == "tok-123"
    m.assert_called_once_with({"k": "v"}, tool_name="owa-mail", audience="outlook")


def test_token_for_returns_empty_on_failure() -> None:
    with patch("owa_tui.adapter.access_token_for", side_effect=RuntimeError("boom")):
        out = token_for({}, tool_name="owa-graph", audience="graph")
    assert out == ""


def test_token_for_never_raises_on_empty_token() -> None:
    with patch("owa_tui.adapter.access_token_for", return_value=""):
        assert token_for({}, tool_name="t", audience="graph") == ""
