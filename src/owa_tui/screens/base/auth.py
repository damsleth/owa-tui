"""auth.py — thin synchronous auth helper for @work(thread=True) workers.

Wraps ``owa_tui.adapter.access_token_for`` so that tool screens do not
need to import the adapter directly, and so that tests can monkeypatch
a single call-site.

Usage inside a @work(thread=True) body::

    from owa_tui.screens.base.auth import token_for

    token = token_for(config, tool_name="owa-mail", audience="outlook")
    if not token:
        self.app.call_from_thread(lambda: setattr(self, "status", "auth failed"))
        return
"""

from __future__ import annotations

from typing import Any


def token_for(
    config: dict[str, Any],
    *,
    tool_name: str,
    audience: str,
) -> str:
    """Return a bearer token string for *tool_name* / *audience*.

    Delegates to ``owa_tui.adapter.access_token_for``.  Returns an empty
    string on failure (never raises) so callers can do a simple falsy check.

    This function is intended to be called from a ``@work(thread=True)``
    worker — it blocks until the token is available.
    """
    try:
        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        return access_token_for(config, tool_name=tool_name, audience=audience)
    except Exception:
        return ""
