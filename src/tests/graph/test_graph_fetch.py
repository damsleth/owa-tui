"""Tests for graph fetch layer: TP11 and related."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from owa_tui.graph.fetch import fetch_items
from owa_tui.graph.state import GraphState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(audience: str = "graph", path: str = "users") -> GraphState:
    return GraphState(config={}, audience=audience, path=path)


def _make_token() -> MagicMock:
    tok = MagicMock()
    tok.access_token = "fake-access-token"
    tok.exp_epoch = 9999999
    return tok


# ---------------------------------------------------------------------------
# TP11: fetch_sets_response_and_kind
# ---------------------------------------------------------------------------


def test_fetch_sets_response_and_kind() -> None:
    """TP11: success path; state.response is set and state.kind == 'collection'."""
    state = _make_state(audience="graph", path="users")

    payload = {"value": [{"id": "u1", "displayName": "Alice"}]}

    fake_token = _make_token()

    with (
        patch("owa_tui.graph.fetch._ensure_token", return_value=fake_token),
        patch(
            "owa_graph.api.api_request",
            return_value=payload,
        ),
    ):
        fetch_items(state)

    assert state.kind == "collection"
    assert state.response is payload
    assert len(state.items) >= 1
    assert not state.dirty


def test_fetch_object_response() -> None:
    """Fetching an object (non-collection) sets kind='object'."""
    state = _make_state(audience="graph", path="me")

    payload = {"id": "u1", "displayName": "Alice", "mail": "alice@example.com"}
    fake_token = _make_token()

    with (
        patch("owa_tui.graph.fetch._ensure_token", return_value=fake_token),
        patch("owa_graph.api.api_request", return_value=payload),
    ):
        fetch_items(state)

    assert state.kind == "object"
    assert state.response is payload


def test_fetch_sets_dirty_false() -> None:
    """After fetch, state.dirty is always False."""
    state = _make_state()
    state.dirty = True

    fake_token = _make_token()
    with (
        patch("owa_tui.graph.fetch._ensure_token", return_value=fake_token),
        patch("owa_graph.api.api_request", return_value={"value": []}),
    ):
        fetch_items(state)

    assert not state.dirty


def test_fetch_no_token_sets_empty_items() -> None:
    """When token is None, items is set to [] and dirty=False."""
    state = _make_state()

    with patch("owa_tui.graph.fetch._ensure_token", return_value=None):
        fetch_items(state)

    assert state.items == []
    assert not state.dirty


def test_fetch_aadsts65002_graceful_degradation() -> None:
    """AADSTS65002 → state.status set, state.items == [], loop stays alive."""
    state = _make_state(audience="ic3", path="v1/users/ME/endpoints")

    fake_token = _make_token()
    with (
        patch("owa_tui.graph.fetch._ensure_token", return_value=fake_token),
        patch(
            "owa_graph.api.api_request",
            side_effect=Exception("AADSTS65002 not preauthorized"),
        ),
    ):
        fetch_items(state)

    assert "AADSTS65002" in state.status
    assert state.items == []
    assert not state.dirty


def test_fetch_aadsts53003_graceful_degradation() -> None:
    """AADSTS53003 → state.status set, state.items == []."""
    state = _make_state(audience="azure", path="subscriptions")

    fake_token = _make_token()
    with (
        patch("owa_tui.graph.fetch._ensure_token", return_value=fake_token),
        patch(
            "owa_graph.api.api_request",
            side_effect=Exception("AADSTS53003 conditional access"),
        ),
    ):
        fetch_items(state)

    assert "AADSTS53003" in state.status
    assert state.items == []


def test_fetch_unknown_audience_returns_immediately() -> None:
    """Unknown audience sets status and returns with empty items."""
    state = _make_state(audience="nonexistent", path="test")

    with patch("owa_tui.graph.fetch._ensure_token") as mock_ensure:
        fetch_items(state)

    mock_ensure.assert_not_called()
    assert "unknown audience" in state.status
    assert state.items == []
