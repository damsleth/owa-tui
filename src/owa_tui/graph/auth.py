"""Graph explorer token cache and auth layer.

Port of ``TokenInfo``, ``_ensure_token``, ``_apply_token``, and
``_exp_epoch_from_broker`` from ``owa_graph.tui``.

No Textual imports — fully unit-testable without a running app.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from owa_tui.graph.state import GraphState

_DEFAULT_TTL = 300  # seconds
_EXP_SKEW = 60  # seconds — evict this many seconds before real expiry


# ---------------------------------------------------------------------------
# TokenInfo
# ---------------------------------------------------------------------------


@dataclass
class TokenInfo:
    """Cached access token with expiry epoch."""

    access_token: str
    exp_epoch: int


# ---------------------------------------------------------------------------
# Helper: extract expiry epoch from a BrokerToken / dict
# ---------------------------------------------------------------------------


def _exp_epoch_from_broker(broker: Any, now: float) -> int:
    """Return Unix expiry epoch from *broker* (BrokerToken or dict).

    Preference order:
    1. ``broker.expires_at`` (absolute timestamp)
    2. ``now + broker.expires_in`` (relative seconds)
    3. ``now + _DEFAULT_TTL`` (fallback)

    Never raises — all missing/None values fall through to the default.
    """
    # Support both attribute-access (BrokerToken dataclass) and dict-style.
    def _get(key: str) -> Any:
        if isinstance(broker, dict):
            return broker.get(key)
        return getattr(broker, key, None)

    expires_at = _get("expires_at")
    if expires_at is not None:
        try:
            return int(expires_at)
        except (TypeError, ValueError):
            pass

    expires_in = _get("expires_in")
    if expires_in is not None:
        try:
            return int(now + float(expires_in))
        except (TypeError, ValueError):
            pass

    return int(now + _DEFAULT_TTL)


# ---------------------------------------------------------------------------
# State mutation helpers
# ---------------------------------------------------------------------------


def _apply_token(state: "GraphState", audience: str, info: TokenInfo) -> None:
    """Store *info* in the token cache on *state* and update expiry."""
    state.token_cache[audience] = info
    state.exp_epoch = info.exp_epoch


# ---------------------------------------------------------------------------
# Main entry point: ensure a valid token exists
# ---------------------------------------------------------------------------


def _ensure_token(audience: str, state: "GraphState") -> TokenInfo | None:
    """Return a valid ``TokenInfo`` for *audience*, minting if necessary.

    Cache hit: ``time.time() < info.exp_epoch - _EXP_SKEW``
    Cache miss / expired: call ``get_token_for_config``.

    On any failure: sets ``state.status``, evicts the cache entry, returns
    ``None`` — never raises.
    """
    now = time.time()

    # Cache hit?
    cached = state.token_cache.get(audience)
    if cached is not None and now < cached.exp_epoch - _EXP_SKEW:
        return cached

    # Need to mint.
    state.status = f"minting token for {audience!r}…"
    try:
        from owa_core.auth import get_token_for_config  # type: ignore[import]

        broker = get_token_for_config(
            state.config,
            tool_name="graph",
            audience=audience,
        )
        if broker is None:
            state.status = f"auth failed: no token returned for {audience!r}"
            state.token_cache.pop(audience, None)
            return None

        def _get_access_token(b: Any) -> str | None:
            if isinstance(b, dict):
                return b.get("access_token")
            return getattr(b, "access_token", None)

        access_token = _get_access_token(broker)
        if not access_token:
            state.status = f"auth failed: empty access_token for {audience!r}"
            state.token_cache.pop(audience, None)
            return None

        exp_epoch = _exp_epoch_from_broker(broker, now)
        info = TokenInfo(access_token=access_token, exp_epoch=exp_epoch)
        _apply_token(state, audience, info)
        return info

    except Exception as exc:
        # Check for AADSTS error codes that mean permanent denial.
        msg = str(exc)
        if "AADSTS65002" in msg:
            state.status = f"AADSTS65002: {audience!r} not preauthorized — try another audience"
        elif "AADSTS53003" in msg:
            state.status = f"AADSTS53003: conditional access blocks {audience!r}"
        elif "token expired" in msg.lower() or "expired" in msg.lower():
            state.status = "token expired"
        else:
            state.status = f"token error: {exc}"
        state.token_cache.pop(audience, None)
        return None


# ---------------------------------------------------------------------------
# Token cache dict type alias (for type annotations)
# ---------------------------------------------------------------------------

TokenCache = dict[str, TokenInfo]
_EMPTY_CACHE: dict[str, TokenInfo] = field(default_factory=dict)  # type: ignore[assignment]
