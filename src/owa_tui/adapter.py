"""Adapter layer: the single sanctioned seam onto the owa-tools stable library.

Token minting and the shared 429 retry wrapper live here. Per-tool data fetching lives in each screen's
own fetch module (``screens/cal/fetch.py``, mail inline, ``graph/fetch.py``,
people inline) — see plan 20: v2 tools each get their own ``adapter.py``.
"""

from __future__ import annotations

import contextlib
import contextvars
import time
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

T = TypeVar("T")

# Graph's per-mailbox concurrency budget (4 in-flight requests) is shared by
# every client using the same app id — and owa-piggy's token carries the
# "One Outlook Web" app id, i.e. the same one as Outlook web in the browser.
RATE_LIMIT_HINT = (
    "rate limited (429): this mailbox's request budget is shared with Outlook "
    "web in the browser — close it or retry in a few seconds"
)


def retrying(
    fn: Callable[[], T],
    *,
    on_wait: Callable[[str], None] | None = None,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call *fn*; on ``RateLimitedError`` wait and retry, up to *attempts* tries.

    Blocking — call from a worker thread. After the last attempt re-raises a
    ``RateLimitedError`` carrying :data:`RATE_LIMIT_HINT` so the status bar
    explains the cause instead of a bare "rate limited (429)".
    """
    from owa_core.errors import RateLimitedError  # type: ignore[import]  # noqa: PLC0415

    # ponytail: the owa_core exception drops the Retry-After header; Graph
    # sends 5s for MailboxConcurrency. Upgrade path: owa_core attaches
    # retry_after to RateLimitedError, read it here.
    wait = 5
    for i in range(1, attempts + 1):
        try:
            return fn()
        except RateLimitedError as exc:
            if i == attempts:
                raise RateLimitedError(RATE_LIMIT_HINT) from exc
            if on_wait is not None:
                on_wait(f"rate limited — retrying in {wait}s ({i}/{attempts - 1})")
            sleep(wait)
    raise AssertionError("unreachable")


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

    override = _PROFILE.get()
    if override:
        config = profile_config(config, override)
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


# ---------------------------------------------------------------------------
# Multi-profile fan-out (owa-tui -A / repeated --profile)
# ---------------------------------------------------------------------------
#
# ``config["owa_piggy_profiles"]`` (a list, may contain "all") puts list
# screens in merged mode. Each fetch runs once per eligible profile with the
# profile set in a context var that access_token_for honours, so no fetch path
# needs a profile argument. Rows come back tagged ``_profile``; anything done
# to a row afterwards (reply, respond, open) mints with profile_config(row).

ALL_PROFILES = "all"  # reserved, same meaning as in owa-tools
_PROFILE: contextvars.ContextVar[str | None] = contextvars.ContextVar("owa_tui_profile", default=None)


def is_multi(config: dict[str, Any]) -> bool:
    return bool(config.get("owa_piggy_profiles"))


def profile_config(config: dict[str, Any], item_or_alias: Any) -> dict[str, Any]:
    """*config* pinned to one profile: the alias itself, or a row's ``_profile``.

    Drops the merged-mode list so a screen pushed for one row (a thread, a
    message) doesn't fan out again. Returns *config* unchanged when there is no
    profile to pin.
    """
    alias = item_or_alias.get("_profile") if isinstance(item_or_alias, dict) else item_or_alias
    if not alias:
        return config
    out = {k: v for k, v in config.items() if k != "owa_piggy_profiles"}
    out["owa_piggy_profile"] = alias
    return out


@contextlib.contextmanager
def as_profile(alias: str | None) -> Iterator[None]:
    """Mint tokens as *alias* inside the block (no-op for None).

    Always reset: worker threads are pooled, and a leaked value would mint the
    next fetch's tokens for the wrong profile.
    """
    if not alias:
        yield
        return
    token = _PROFILE.set(alias)
    try:
        yield
    finally:
        _PROFILE.reset(token)


def _eligible(row: Any, service: str) -> bool:
    """owa-tools' ``-A`` rule: registered, configured, and offering *service*."""
    if not (row.registered and row.has_config):
        return False
    if row.services:
        return service in row.services
    return row.type == ("ado" if service == "ado" else "m365")  # older brokers omit services


def eligible_profiles(config: dict[str, Any], service: str = "owa") -> list[str]:
    """Expand ``owa_piggy_profiles`` ("all" → every eligible profile), de-duplicated.

    Blocking (shells out to owa-piggy); call from a worker. Fixture mode reads
    ``profiles.json`` (a list of broker rows) instead.
    """
    from owa_tui import fixtures  # noqa: PLC0415

    requested = list(config.get("owa_piggy_profiles") or [])
    if ALL_PROFILES in requested:
        if fixtures.enabled():
            from types import SimpleNamespace  # noqa: PLC0415

            rows: list[Any] = [
                SimpleNamespace(**{"type": "m365", "services": (), **r})
                for r in fixtures.load("profiles") or []
            ]
        else:
            from owa_core.auth import get_profiles  # type: ignore[import]  # noqa: PLC0415

            rows = get_profiles(tool_name="owa-tui")
        eligible = [r.alias for r in rows if _eligible(r, service)]
    else:
        eligible = []
    out: list[str] = []
    for value in requested:  # explicit names are kept even if ineligible: they error visibly
        for name in eligible if value == ALL_PROFILES else [value]:
            if name not in out:
                out.append(name)
    return out


def fan_out(
    config: dict[str, Any], fetch: Callable[[], list[dict]], *, service: str = "owa"
) -> tuple[list[dict], list[str]]:
    """Run *fetch* once per eligible profile; return (tagged rows, "alias: error" list).

    Blocking — call from a worker thread. A profile that fails doesn't sink the
    others; its error comes back for the status line.
    """
    rows: list[dict] = []
    errors: list[str] = []
    for alias in eligible_profiles(config, service):
        with as_profile(alias):
            try:
                got = fetch()
            except Exception as exc:  # noqa: BLE001 — reported per profile
                errors.append(f"{alias}: {exc}")
                continue
        for row in got:
            row["_profile"] = alias
        rows.extend(got)
    return rows, errors


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
