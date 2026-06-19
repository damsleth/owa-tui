"""Graph explorer fetch layer.

``fetch_items(state)`` is the single public entry point.
It mints a token, builds the URL, calls the Graph API, classifies the
response, and mutates *state*.  It never raises — all failures land in
``state.status``.

No Textual imports — fully unit-testable without a running app.
"""

from __future__ import annotations

from owa_tui.graph.auth import _ensure_token
from owa_tui.graph.nav import build_rows, classify_response, extract_next_link
from owa_tui.graph.state import GraphState

# Audience -> base URL mapping (mirrors owa_graph.auth.AUDIENCE_API_BASE)
AUDIENCE_API_BASE: dict[str, str] = {
    "graph": "https://graph.microsoft.com/v1.0",
    "outlook": "https://outlook.office.com/api/v2.0",
    "outlook365": "https://outlook.office365.com/api/v2.0",
    "teams": "https://api.spaces.skype.com",
    "ic3": "https://ic3.teams.office.com",
    "csa": "https://chatsvcagg.teams.microsoft.com",
    "presence": "https://presence.teams.microsoft.com",
    "uis": "https://uis.teams.microsoft.com",
    "azure": "https://management.azure.com",
    "keyvault": "https://vault.azure.net",
    "storage": "https://storage.azure.com",
    "sql": "https://database.windows.net",
    "substrate": "https://substrate.office.com",
    "manage": "https://manage.office.com/api/v1.0",
    "powerbi": "https://api.powerbi.com/v1.0",
    "flow": "https://service.flow.microsoft.com",
    "devops": "https://app.vssps.visualstudio.com",
}

# Tier D audiences — raw request targets, not browse surfaces
_TIER_D = frozenset({"keyvault", "storage", "sql"})


def _build_url(api_base: str, path: str, query: str = "") -> str:
    """Construct the full request URL."""
    base = api_base.rstrip("/")
    path_part = path.strip("/")
    url = f"{base}/{path_part}" if path_part else base
    if query:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query}"
    return url


def fetch_items(state: GraphState) -> None:
    """Fetch one page of results for the current state, mutating *state*.

    Steps:
    1. Ensure a valid token (``_ensure_token``).
    2. Build URL from ``state.audience``, ``state.path``, ``state.query``.
    3. If ``state.next_link`` is set, use that URL instead (pagination).
    4. Call ``owa_graph.api.api_request`` (GET).
    5. Classify response and build rows.
    6. Update ``state.items``, ``state.kind``, ``state.response``,
       ``state.next_link``, ``state.status``, ``state.dirty``.
    """
    audience = state.audience
    api_base = AUDIENCE_API_BASE.get(audience, "")
    if not api_base:
        state.status = f"unknown audience: {audience!r}"
        state.items = []
        return

    # Tier D — show notice in status; still attempt the request
    if audience in _TIER_D:
        state.status = "Tier D: raw target — not a browse surface"

    # 1. Token
    token_info = _ensure_token(audience, state)
    if token_info is None:
        state.items = []
        state.dirty = False
        return

    access_token = token_info.access_token

    # 2/3. URL
    if state.next_link:
        url = state.next_link
    else:
        url = _build_url(api_base, state.path, state.query)

    # 4. API call
    try:
        from owa_tui import fixtures  # noqa: PLC0415

        result = fixtures.graph(state.path) if fixtures.enabled() else None
        if result is None:
            from owa_graph.api import api_request  # type: ignore[import]

            result = api_request(
                "GET",
                api_base,
                url.replace(api_base, "").lstrip("/") if url.startswith(api_base) else url,
                access_token,
                debug=state.debug,
            )
        # api_request may return the parsed dict/list or raise on HTTP error
        state.response = result

        # If result is bytes-like, classify from raw bytes; else wrap as JSON
        import json

        if isinstance(result, (bytes, bytearray)):
            raw_bytes = bytes(result)
        elif result is None:
            raw_bytes = b""
        else:
            raw_bytes = json.dumps(result).encode()

        kind, payload = classify_response(raw_bytes)
        state.kind = kind

        # 5. Build rows
        rows = build_rows(kind, payload, audience=audience, audience_base=api_base)
        state.items = rows

        # 6. Pagination cursor
        response_headers: dict[str, str] = {}
        next_link = extract_next_link(kind, payload if isinstance(payload, dict) else {}, audience, response_headers)
        state.next_link = next_link

        if not state.status or state.status.startswith("Tier D"):
            state.status = f"{audience}:{state.path} — {len(rows)} items"

    except Exception as exc:
        msg = str(exc)
        if "AADSTS65002" in msg:
            state.status = f"AADSTS65002: {audience!r} not preauthorized — try another audience"
            state.items = []
        elif "AADSTS53003" in msg:
            state.status = f"AADSTS53003: conditional access blocks {audience!r}"
            state.items = []
        else:
            state.status = f"fetch error: {exc}"
            state.items = []
        state.token_cache.pop(audience, None)

    state.dirty = False
