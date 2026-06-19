"""Adapter layer: in-process wrappers over the owa-tools stable library surface.

All public async functions return ``(result, error_str | None)`` and never raise.
Blocking owa-tools calls are dispatched with ``asyncio.to_thread`` so the
Textual event loop is never stalled.

The ``FetchMixin`` class is a Textual ``Widget``/``Screen`` mixin that provides
``load_data()``, a ``@work(exclusive=True)`` async worker screens use as a base.

Usage from a Screen
-------------------
    class MyScreen(Screen, FetchMixin):
        def on_mount(self) -> None:
            self.load_data()
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def access_token_for(config: dict[str, Any], *, tool_name: str, audience: str) -> str:
    """Mint a fresh bearer token via owa-piggy and return the access_token string.

    owa-piggy owns the token lifecycle, so this shells out (via
    ``get_token_for_config``) on every call rather than caching. Returns ``""``
    on failure. Blocking — call from a worker thread.

    Handles the broker return shape: a frozen ``BrokerToken`` dataclass (current
    contract), a dict, or a bare string. The dataclass case is why ``.get()``
    silently failed for mail/cal before — ``getattr`` is the correct accessor.
    """
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


async def fetch_token(config: dict[str, Any], tool_name: str, audience: str) -> tuple[Any, str | None]:
    """Mint or refresh an owa-tools token off the event loop thread.

    Returns ``(token_info, None)`` on success or ``(None, error_str)`` on failure.
    """
    try:
        from owa_core.auth import get_token_for_config  # type: ignore[import]

        token_info = await asyncio.to_thread(
            get_token_for_config, config, tool_name=tool_name, audience=audience
        )
        if token_info is None:
            return None, "auth failed: get_token_for_config returned None"
        return token_info, None
    except Exception as exc:  # pragma: no cover
        return None, f"auth error: {exc}"


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


async def fetch_cal_events(
    access_token: str,
    api_base: str,
    day_range: int = 7,
    show_declined: bool = False,
    search: str = "",
    debug: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch calendar events from the Graph API.

    Returns ``(events, None)`` on success or ``([], error_str)`` on failure.
    All blocking network I/O runs in a thread.
    """
    try:
        from owa_cal.api import api_get  # type: ignore[import]
        from owa_cal.events import normalize_events  # type: ignore[import]

        params: dict[str, Any] = {"dayRange": day_range, "showDeclined": show_declined}
        if search:
            params["search"] = search

        def _call() -> Any:
            return api_get(api_base, "me/calendarView", access_token, params=params, debug=debug)

        raw = await asyncio.to_thread(_call)
        if raw is None:
            return [], "no data returned from calendar API"
        events = normalize_events(raw) if isinstance(raw, list) else []
        return events, None
    except Exception as exc:
        return [], f"calendar fetch error: {exc}"


# ---------------------------------------------------------------------------
# Mail
# ---------------------------------------------------------------------------


async def fetch_mail_messages(
    access_token: str,
    api_base: str,
    folder: str = "Inbox",
    top: int = 50,
    search: str = "",
    debug: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch mail messages from the Graph API.

    Returns ``(messages, None)`` on success or ``([], error_str)`` on failure.
    """
    try:
        from owa_mail.api import api_get  # type: ignore[import]
        from owa_mail.messages import build_list_query, normalize_messages  # type: ignore[import]

        query = build_list_query(folder=folder, top=top, search=search if search else None)

        def _call() -> Any:
            return api_get(api_base, query, access_token, debug=debug)

        raw = await asyncio.to_thread(_call)
        if raw is None:
            return [], "no data returned from mail API"
        messages = normalize_messages(raw) if isinstance(raw, list) else []
        return messages, None
    except Exception as exc:
        return [], f"mail fetch error: {exc}"


# ---------------------------------------------------------------------------
# Graph (generic)
# ---------------------------------------------------------------------------


async def fetch_graph_request(
    access_token: str,
    api_base: str,
    endpoint: str,
    debug: bool = False,
) -> tuple[Any, str | None]:
    """Execute a generic Graph API request off the event loop thread.

    Returns ``(data, None)`` on success or ``(None, error_str)`` on failure.
    """
    try:
        from owa_graph.api import api_request  # type: ignore[import]

        def _call() -> Any:
            return api_request(api_base, endpoint, access_token, debug=debug)

        data = await asyncio.to_thread(_call)
        return data, None
    except Exception as exc:
        return None, f"graph fetch error: {exc}"


# ---------------------------------------------------------------------------
# FetchMixin
# ---------------------------------------------------------------------------


class FetchMixin:
    """Mixin for Textual ``Screen``/``Widget`` subclasses providing a standard
    async-fetch / call-back worker pattern.

    Subclasses must implement ``_do_fetch()`` (an async function that returns
    ``(result, error_str | None)``) and ``_apply_fetch_result(result, error)``.

    The ``load_data()`` method is a ``@work(exclusive=True)`` worker that calls
    ``_do_fetch``, then posts ``_apply_fetch_result`` to the main event loop via
    ``call_from_thread``.  This ensures blocking owa-tools I/O never stalls the UI.

    Example
    -------
        class CalScreen(Screen, FetchMixin):
            async def _do_fetch(self):
                return await fetch_cal_events(self._token, self._api_base)

            def _apply_fetch_result(self, result, error):
                self._events = result
                self._status = error or ''
    """

    async def _do_fetch(self) -> tuple[Any, str | None]:  # pragma: no cover
        """Override in subclasses. Returns (result, error_str | None)."""
        return None, "not implemented"

    def _apply_fetch_result(self, result: Any, error: str | None) -> None:  # pragma: no cover
        """Override in subclasses. Called on the main loop after fetch."""

    def load_data(self) -> None:
        """Launch the async-fetch worker. Must be called from the event loop."""
        from textual.worker import work as _work  # type: ignore[import]

        # Dynamically create and invoke a @work(exclusive=True) coroutine so
        # FetchMixin does not need to be a Textual Widget at import time.
        async def _worker(self: "FetchMixin") -> None:
            result, error = await self._do_fetch()
            # call_from_thread posts back to the main event loop
            self.app.call_from_thread(self._apply_fetch_result, result, error)  # type: ignore[attr-defined]

        # Use Textual's work() decorator programmatically
        worker_fn = _work(exclusive=True)(_worker)
        worker_fn(self)
