"""Graph explorer navigation helpers.

Ported from ``owa_graph.tui_nav``:
- ``next_path`` — breadcrumb/URL resolution
- ``classify_response`` — determine response kind
- ``build_rows`` — build drillable rows from payload
- ``Row`` — named tuple for list items
- ``_header_get`` — case-insensitive header lookup

Pagination cursor extraction (3 shapes):
- OData: ``payload['@odata.nextLink']``
- ARM:   ``payload['nextLink']``
- DevOps: ``x-ms-continuationtoken`` response header → ``?continuationToken=<value>``

No Textual imports — fully unit-testable without a running app.
"""

from __future__ import annotations

from typing import Any, NamedTuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ROWS = 500
MAX_KEYS = 100

# Fields that must never appear as drill targets
_DENY_LIST = frozenset(
    {
        "@odata.context",
        "@odata.editLink",
        "editLink",
        "@odata.type",
        "type",
        "metadata",
        "etag",
        "@odata.etag",
        "@odata.count",
        "count",
        "@odata.id",
    }
)

# Human-readable label fields (tried in order)
_LABEL_FIELDS = (
    "displayName",
    "name",
    "subject",
    "title",
    "givenName",
    "userPrincipalName",
    "mail",
    "id",
)

# Audiences that serve OData pagination
_ODATA_AUDIENCES = frozenset(
    {
        "graph",
        "outlook",
        "outlook365",
        "powerbi",
        "flow",
        "manage",
        "substrate",
    }
)

# ARM audiences
_ARM_AUDIENCES = frozenset({"azure", "keyvault", "storage", "sql"})

# DevOps
_DEVOPS_AUDIENCES = frozenset({"devops"})


# ---------------------------------------------------------------------------
# Row
# ---------------------------------------------------------------------------


class Row(NamedTuple):
    """A single item in the list browser.

    Attributes
    ----------
    label:
        Display text for the row.
    drill_target:
        URL or path to navigate to on drill, or ``None`` if not drillable.
    drillable:
        ``True`` when the row can be opened (Enter/→).
    dim:
        ``True`` for navigation-link rows (shown dimmed).
    """

    label: str
    drill_target: str | None
    drillable: bool
    dim: bool = False


# ---------------------------------------------------------------------------
# Case-insensitive header lookup
# ---------------------------------------------------------------------------


def _header_get(headers: dict[str, str] | Any, key: str) -> str | None:
    """Return header value for *key* using case-insensitive lookup."""
    if not headers:
        return None
    lower_key = key.lower()
    if isinstance(headers, dict):
        for k, v in headers.items():
            if k.lower() == lower_key:
                return v
    return None


# ---------------------------------------------------------------------------
# next_path: breadcrumb URL resolution
# ---------------------------------------------------------------------------


def next_path(current_path: str | None, target: str) -> str:
    """Resolve *target* relative to *current_path*.

    Rules:
    - Absolute URL (``http://`` / ``https://``) → returned verbatim
    - Absolute path (starts with ``/``) → returned verbatim
    - Relative segment → appended to ``current_path`` with ``/``
    """
    if not target:
        return current_path or ""
    if target.startswith("https://") or target.startswith("http://"):
        return target
    if target.startswith("/"):
        return target
    cur = (current_path or "").strip("/")
    return f"{cur}/{target}" if cur else target


# ---------------------------------------------------------------------------
# classify_response
# ---------------------------------------------------------------------------


def classify_response(body: bytes | None) -> tuple[str, Any]:
    """Classify raw response bytes into (kind, payload).

    Kinds:
    - ``'collection'``: dict with ``value`` list, or bare list
    - ``'object'``: dict without ``value`` list
    - ``'scalar'``: non-dict, non-list JSON primitive
    - ``'opaque'``: non-JSON bytes
    - ``'empty'``: empty / None body (returned as ``('object', {})``)
    """
    import json

    if not body:
        return "object", {}

    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return "opaque", body

    if isinstance(payload, list):
        return "collection", payload
    if isinstance(payload, dict):
        if isinstance(payload.get("value"), list):
            return "collection", payload
        return "object", payload
    # scalar (str, int, float, bool, None)
    return "scalar", payload


# ---------------------------------------------------------------------------
# _is_nav_link_key: identify navigation/association link keys
# ---------------------------------------------------------------------------


def _is_nav_link_key(key: str) -> bool:
    """Return True if *key* is a navigation or association link field."""
    if key.endswith("@odata.navigationLink"):
        return True
    if key.endswith("@odata.associationLink"):
        return True
    if key in ("@odata.nextLink", "nextLink"):
        return True
    return False


def _is_cross_host_url(value: Any, audience_base: str = "") -> bool:
    """Return True if *value* is an absolute URL pointing to a different host."""
    if not isinstance(value, str):
        return False
    if not (value.startswith("http://") or value.startswith("https://")):
        return False
    # If audience_base is provided, URLs to the same host are drillable
    if audience_base:
        try:
            from urllib.parse import urlparse

            base_host = urlparse(audience_base).netloc
            val_host = urlparse(value).netloc
            if base_host and base_host == val_host:
                return False  # same host — drillable
        except Exception:
            pass
    return True  # cross-host CDN/photo/portal URL


# ---------------------------------------------------------------------------
# build_rows: convert payload to drillable Row list
# ---------------------------------------------------------------------------


def build_rows(kind: str, payload: Any, audience: str = "", audience_base: str = "") -> list[Row]:
    """Build drillable ``Row`` list from classified *payload*.

    Parameters
    ----------
    kind:
        Result of :func:`classify_response`.
    payload:
        The decoded payload (list, dict, scalar, or raw bytes).
    audience:
        Active audience key (used for deny-list and cross-host detection).
    audience_base:
        Base URL for the audience (used for same-host drill detection).
    """
    if kind == "opaque":
        return [Row("(opaque binary response)", None, False)]

    if kind == "scalar":
        return [Row(str(payload), None, False)]

    if kind == "collection":
        items: list[Any] = payload if isinstance(payload, list) else payload.get("value", [])
        if not items:
            return [Row("(no items — press r to retry, a to switch audience)", None, False)]
        rows: list[Row] = []
        for item in items[:MAX_ROWS]:
            if not isinstance(item, dict):
                rows.append(Row(str(item), None, False))
                continue
            # Choose label
            label = ""
            for lf in _LABEL_FIELDS:
                if lf in item and item[lf] is not None:
                    label = str(item[lf])
                    break
            if not label:
                label = str(item)[:80]

            # Drill target preference: @odata.id then id
            drill_target = None
            for key in ("@odata.id", "id"):
                val = item.get(key)
                if val and isinstance(val, str):
                    drill_target = val
                    break
            drillable = drill_target is not None
            rows.append(Row(label, drill_target, drillable))

        if len(items) > MAX_ROWS:
            rows.append(Row(f"… {len(items) - MAX_ROWS} more items (capped at {MAX_ROWS})", None, False, True))
        return rows

    if kind == "object":
        d: dict[str, Any] = payload if isinstance(payload, dict) else {}
        if not d:
            return [Row("(empty object)", None, False)]
        rows = []
        for i, (key, val) in enumerate(d.items()):
            if i >= MAX_KEYS:
                rows.append(Row(f"… {len(d) - MAX_KEYS} more keys (capped at {MAX_KEYS})", None, False, True))
                break
            if key in _DENY_LIST:
                continue
            if _is_nav_link_key(key):
                # Navigation link — show as dim, drillable if value is a URL
                target = val if isinstance(val, str) else None
                rows.append(Row(f"{key}: {val}", target, bool(target), True))
                continue
            # Check for cross-host absolute URLs → detail only, not drillable
            if _is_cross_host_url(val, audience_base):
                rows.append(Row(f"{key}: {val}", None, False, True))
                continue
            # Value is a dict → drillable if it has @odata.id or can be path-appended
            if isinstance(val, dict):
                sub_id = val.get("@odata.id") or val.get("id")
                target = str(sub_id) if sub_id else key
                rows.append(Row(f"{key}: {str(val)[:60]}", target, True))
            elif isinstance(val, list):
                rows.append(Row(f"{key}: [{len(val)} items]", key, True))
            elif isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                # Same-host or relative URL
                rows.append(Row(f"{key}: {val}", val, True))
            else:
                rows.append(Row(f"{key}: {val}", None, False))
        if not rows:
            return [Row("(no items — press r to retry, a to switch audience)", None, False)]
        return rows

    return [Row("(unknown response kind)", None, False)]


# ---------------------------------------------------------------------------
# Pagination cursor extraction
# ---------------------------------------------------------------------------


def extract_next_link(
    kind: str,
    payload: Any,
    audience: str,
    response_headers: dict[str, str] | None = None,
) -> str | None:
    """Extract the pagination cursor for the next page.

    Shapes:
    - OData audiences: ``payload['@odata.nextLink']``
    - ARM audiences: ``payload['nextLink']``
    - DevOps: ``x-ms-continuationtoken`` header → ``?continuationToken=<value>``
    """
    if not isinstance(payload, dict):
        return None

    if audience in _DEVOPS_AUDIENCES:
        token = _header_get(response_headers or {}, "x-ms-continuationtoken")
        if token:
            return f"?continuationToken={token}"
        return None

    if audience in _ARM_AUDIENCES:
        return payload.get("nextLink") or None

    # OData (default)
    return payload.get("@odata.nextLink") or None


# ---------------------------------------------------------------------------
# Navigation actions: on_drill / on_back
# ---------------------------------------------------------------------------


def on_drill(state: Any, item: Row) -> bool:
    """Push current position onto history, then navigate to *item*.

    Returns ``True`` if navigation happened, ``False`` if *item* is not drillable.
    """
    if not item.drillable or item.drill_target is None:
        return False

    # Push 7-tuple
    state.history.append(
        (
            state.audience,
            state.path,
            state.query,
            state.selected,
            state.top,
            list(state.items),
            state.next_link,
        )
    )

    # Navigate
    new_path = next_path(state.path, item.drill_target)
    state.path = new_path
    state.selected = 0
    state.top = 0
    state.next_link = None
    state.dirty = True
    return True


def on_back(state: Any) -> bool:
    """Pop the most recent history frame, restoring all 7 fields.

    Returns ``False`` (without modifying state) if history is empty.
    The restored state has ``dirty=False`` so ``fetch_items`` is not re-triggered.
    """
    if not state.history:
        return False

    audience, path, query, selected, top, rows, next_link = state.history.pop()
    state.audience = audience
    state.path = path
    state.query = query
    state.selected = selected
    state.top = top
    state.items = rows
    state.next_link = next_link
    state.dirty = False
    return True
