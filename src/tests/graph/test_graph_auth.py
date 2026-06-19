"""Tests for graph auth layer: TP1–TP6."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from owa_tui.graph.auth import (
    _DEFAULT_TTL,
    TokenInfo,
    _ensure_token,
    _exp_epoch_from_broker,
)
from owa_tui.graph.state import GraphState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**kwargs: object) -> GraphState:
    return GraphState(config={}, **kwargs)  # type: ignore[arg-type]


def _make_token(ttl: int = 600) -> TokenInfo:
    return TokenInfo(access_token="tok-abc", exp_epoch=int(time.time()) + ttl)


# ---------------------------------------------------------------------------
# TP1: cache hit does not trigger a re-mint
# ---------------------------------------------------------------------------


def test_cache_hit_no_remint() -> None:
    """TP1: _ensure_token returns cached token without calling get_token_for_config."""
    state = _make_state()
    fresh_token = _make_token(ttl=600)
    state.token_cache["graph"] = fresh_token

    with patch("owa_core.auth.get_token_for_config") as mock_mint:
        result = _ensure_token("graph", state)

    assert result is fresh_token
    mock_mint.assert_not_called()


# ---------------------------------------------------------------------------
# TP2: cache miss mints and populates
# ---------------------------------------------------------------------------


def test_miss_mints_and_populates() -> None:
    """TP2: cache miss calls get_token_for_config and caches the result."""
    state = _make_state()
    assert "graph" not in state.token_cache

    fake_broker = MagicMock()
    fake_broker.access_token = "new-access-tok"
    fake_broker.expires_at = None
    fake_broker.expires_in = 3600

    with patch("owa_core.auth.get_token_for_config", return_value=fake_broker) as mock_mint:
        result = _ensure_token("graph", state)

    assert result is not None
    assert result.access_token == "new-access-tok"
    assert "graph" in state.token_cache
    mock_mint.assert_called_once()


# ---------------------------------------------------------------------------
# TP3: failure returns None, evicts cache, sets status
# ---------------------------------------------------------------------------


def test_failure_returns_none_evicts() -> None:
    """TP3: auth failure returns None, evicts cache entry, sets state.status."""
    state = _make_state()
    # Pre-populate cache with stale token so it will be evicted on re-mint failure
    state.token_cache["graph"] = TokenInfo(access_token="old", exp_epoch=1)  # expired

    with patch(
        "owa_core.auth.get_token_for_config",
        side_effect=Exception("token expired"),
    ):
        result = _ensure_token("graph", state)

    assert result is None
    assert "graph" not in state.token_cache
    assert "token expired" in state.status or state.status != ""


# ---------------------------------------------------------------------------
# TP4: per-audience keying
# ---------------------------------------------------------------------------


def test_per_audience_keying() -> None:
    """TP4: cached graph token does not satisfy azure request."""
    state = _make_state()
    state.token_cache["graph"] = _make_token(ttl=600)

    fake_broker = MagicMock()
    fake_broker.access_token = "azure-tok"
    fake_broker.expires_at = None
    fake_broker.expires_in = 3600

    with patch("owa_core.auth.get_token_for_config", return_value=fake_broker) as mock_mint:
        result = _ensure_token("azure", state)

    assert result is not None
    assert result.access_token == "azure-tok"
    mock_mint.assert_called_once()
    # Graph token is still in cache
    assert "graph" in state.token_cache


# ---------------------------------------------------------------------------
# TP5: expires_at=None + expires_in=None → uses _DEFAULT_TTL, no TypeError
# ---------------------------------------------------------------------------


def test_no_expires_fields_uses_default_ttl() -> None:
    """TP5: missing expires_at and expires_in falls back to _DEFAULT_TTL."""
    now = time.time()
    broker: dict = {"access_token": "tok", "expires_at": None, "expires_in": None}
    epoch = _exp_epoch_from_broker(broker, now)
    assert abs(epoch - int(now + _DEFAULT_TTL)) <= 1


# ---------------------------------------------------------------------------
# TP6: expiry skew forces re-mint
# ---------------------------------------------------------------------------


def test_expiry_skew_forces_remint() -> None:
    """TP6: token within EXP_SKEW seconds of expiry is treated as expired."""
    state = _make_state()
    # Token expiring in 30s (< EXP_SKEW=60)
    nearly_expired = TokenInfo(access_token="old", exp_epoch=int(time.time()) + 30)
    state.token_cache["graph"] = nearly_expired

    fake_broker = MagicMock()
    fake_broker.access_token = "fresh-tok"
    fake_broker.expires_at = None
    fake_broker.expires_in = 3600

    with patch("owa_core.auth.get_token_for_config", return_value=fake_broker) as mock_mint:
        result = _ensure_token("graph", state)

    assert result is not None
    assert result.access_token == "fresh-tok"
    mock_mint.assert_called_once()


# ---------------------------------------------------------------------------
# TP_A: AADSTS65002 graceful degradation
# ---------------------------------------------------------------------------


def test_aadsts65002_sets_status() -> None:
    """AADSTS65002 → status set, None returned, no raise."""
    state = _make_state()
    with patch(
        "owa_core.auth.get_token_for_config",
        side_effect=Exception("AADSTS65002 not preauthorized"),
    ):
        result = _ensure_token("ic3", state)

    assert result is None
    assert "AADSTS65002" in state.status


def test_aadsts53003_sets_status() -> None:
    """AADSTS53003 → status set, None returned, no raise."""
    state = _make_state()
    with patch(
        "owa_core.auth.get_token_for_config",
        side_effect=Exception("AADSTS53003 conditional access"),
    ):
        result = _ensure_token("azure", state)

    assert result is None
    assert "AADSTS53003" in state.status


# ---------------------------------------------------------------------------
# _exp_epoch_from_broker: prefer expires_at
# ---------------------------------------------------------------------------


def test_exp_epoch_prefers_expires_at() -> None:
    """_exp_epoch_from_broker prefers expires_at over expires_in."""
    now = time.time()
    broker: dict = {"access_token": "t", "expires_at": 9999999, "expires_in": 100}
    epoch = _exp_epoch_from_broker(broker, now)
    assert epoch == 9999999


def test_exp_epoch_uses_expires_in_when_no_expires_at() -> None:
    """_exp_epoch_from_broker uses expires_in when expires_at is None."""
    now = 1000000.0
    broker: dict = {"access_token": "t", "expires_at": None, "expires_in": 3600}
    epoch = _exp_epoch_from_broker(broker, now)
    assert epoch == int(now + 3600)
