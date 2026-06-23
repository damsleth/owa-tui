"""Adapter layer: the single sanctioned seam onto the owa-tools stable library.

Only token minting lives here. Per-tool data fetching lives in each screen's
own fetch module (``screens/cal/fetch.py``, mail inline, ``graph/fetch.py``,
people inline) — see plan 20: v2 tools each get their own ``adapter.py``.
"""

from __future__ import annotations

from typing import Any


def access_token_for(config: dict[str, Any], *, tool_name: str, audience: str) -> str:
    """Mint a fresh bearer token via owa-piggy and return the access_token string.

    owa-piggy owns the token lifecycle, so this shells out (via
    ``get_token_for_config``) on every call rather than caching. Returns ``""``
    on failure. Blocking — call from a worker thread.

    Handles the broker return shape: a frozen ``BrokerToken`` dataclass (current
    contract), a dict, or a bare string. The dataclass case is why ``.get()``
    silently failed for mail/cal before — ``getattr`` is the correct accessor.
    """
    from owa_tui import fixtures  # noqa: PLC0415

    if fixtures.enabled():
        return fixtures.TOKEN
    try:
        from owa_core.auth import get_token_for_config  # type: ignore[import]

        info = get_token_for_config(config, tool_name=tool_name, audience=audience)
    except Exception:
        return ""
    if info is None:
        return ""
    if isinstance(info, str):
        return info
    if isinstance(info, dict):
        return info.get("access_token") or ""
    return getattr(info, "access_token", "") or ""


def current_identity(config: dict[str, Any]) -> tuple[str | None, str | None]:
    """Best-effort ``(profile_alias, upn)`` for the header top row.

    Never raises — returns ``None`` for either field on any failure. Blocking
    (shells out to owa-piggy and decodes a token); call from a worker thread.
    """
    profile: str | None = (config.get("owa_piggy_profile") or "").strip() or None
    upn: str | None = None
    if profile is None:
        try:
            from owa_core.auth import get_profiles  # type: ignore[import]  # noqa: PLC0415

            profiles = get_profiles(tool_name="owa-tui")
            profile = next((p.alias for p in profiles if p.default), None)
        except Exception:
            pass
    try:
        token = access_token_for(config, tool_name="owa-tui", audience="graph")
        upn = _upn_from_jwt(token)
    except Exception:
        pass
    return profile, upn


def _upn_from_jwt(token: str) -> str | None:
    """Extract a user principal name from a JWT's claims, or None."""
    if not token or token.count(".") < 2:
        return None
    import base64  # noqa: PLC0415
    import json  # noqa: PLC0415

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)  # restore base64 padding
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    for key in ("upn", "preferred_username", "unique_name", "email"):
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value
    return None
