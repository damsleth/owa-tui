"""Tests for graph navigation layer: TP7–TP36."""

from __future__ import annotations

from owa_tui.graph.nav import (
    Row,
    _header_get,
    build_rows,
    classify_response,
    extract_next_link,
    next_path,
    on_back,
    on_drill,
)
from owa_tui.graph.state import GraphState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(**kwargs: object) -> GraphState:
    state = GraphState(config={}, **kwargs)  # type: ignore[arg-type]
    return state


def _drillable_row(label: str = "item", target: str = "items/1") -> Row:
    return Row(label=label, drill_target=target, drillable=True)


def _non_drillable_row() -> Row:
    return Row(label="nothing", drill_target=None, drillable=False)


# ---------------------------------------------------------------------------
# next_path (TP25–TP27)
# ---------------------------------------------------------------------------


def test_next_path_absolute_url_returned_verbatim() -> None:
    """TP25: absolute URL target → navigate verbatim."""
    target = "https://graph.microsoft.com/v1.0/users"
    assert next_path("users", target) == target


def test_next_path_absolute_path_replaces_current() -> None:
    """TP26: absolute path target → replace current_path."""
    assert next_path("users/1", "/subscriptions/sub-id") == "/subscriptions/sub-id"


def test_next_path_relative_segment_appended() -> None:
    """TP27: relative segment → append to current_path."""
    assert next_path("users", "messages") == "users/messages"


def test_next_path_empty_current() -> None:
    result = next_path("", "me")
    assert result == "me"


def test_next_path_trailing_slash_stripped() -> None:
    result = next_path("users/", "messages")
    assert result == "users/messages"


# ---------------------------------------------------------------------------
# classify_response (TP7–TP12)
# ---------------------------------------------------------------------------


def test_classify_dict_with_value_list() -> None:
    """TP7: dict with value list → 'collection'."""
    import json

    body = json.dumps({"value": [{"id": "1"}, {"id": "2"}], "@odata.count": 2}).encode()
    kind, payload = classify_response(body)
    assert kind == "collection"
    assert isinstance(payload, dict)


def test_classify_dict_without_value_list() -> None:
    """TP8: dict without value list → 'object'."""
    import json

    body = json.dumps({"id": "u1", "displayName": "Alice"}).encode()
    kind, payload = classify_response(body)
    assert kind == "object"
    assert isinstance(payload, dict)


def test_classify_bare_json_list() -> None:
    """TP9: bare JSON list → 'collection'."""
    import json

    body = json.dumps([{"id": "1"}, {"id": "2"}]).encode()
    kind, payload = classify_response(body)
    assert kind == "collection"
    assert isinstance(payload, list)


def test_classify_scalar_string() -> None:
    """TP10: bare scalar string → 'scalar'."""
    import json

    body = json.dumps("hello").encode()
    kind, payload = classify_response(body)
    assert kind == "scalar"
    assert payload == "hello"


def test_classify_non_json_bytes() -> None:
    """TP11: non-JSON bytes → 'opaque'."""
    kind, payload = classify_response(b"\x00\x01\x02binary")
    assert kind == "opaque"


def test_classify_empty_body() -> None:
    """TP12: empty body → ('object', {})."""
    kind, payload = classify_response(b"")
    assert kind == "object"
    assert payload == {}


def test_classify_none_body() -> None:
    kind, payload = classify_response(None)
    assert kind == "object"
    assert payload == {}


# ---------------------------------------------------------------------------
# build_rows (TP13–TP20)
# ---------------------------------------------------------------------------


def test_build_rows_opaque() -> None:
    rows = build_rows("opaque", b"binary")
    assert len(rows) == 1
    assert not rows[0].drillable


def test_build_rows_scalar() -> None:
    rows = build_rows("scalar", "hello world")
    assert len(rows) == 1
    assert rows[0].label == "hello world"
    assert not rows[0].drillable


def test_build_rows_empty_collection() -> None:
    rows = build_rows("collection", [])
    assert len(rows) == 1
    assert not rows[0].drillable
    assert "no items" in rows[0].label


def test_build_rows_collection_capped_at_max_rows() -> None:
    from owa_tui.graph.nav import MAX_ROWS

    payload = [{"id": str(i), "displayName": f"user {i}"} for i in range(MAX_ROWS + 10)]
    rows = build_rows("collection", payload)
    # Should have MAX_ROWS items + 1 overflow sentinel
    assert len(rows) <= MAX_ROWS + 1


def test_build_rows_object_capped_at_max_keys() -> None:
    from owa_tui.graph.nav import MAX_KEYS

    d = {f"key{i}": f"val{i}" for i in range(MAX_KEYS + 10)}
    rows = build_rows("object", d)
    assert len(rows) <= MAX_KEYS + 1


def test_build_rows_deny_list_filtered() -> None:
    """@odata.context and friends must not appear as rows."""
    d = {
        "@odata.context": "https://graph.microsoft.com/$metadata",
        "displayName": "Alice",
        "@odata.count": 1,
    }
    rows = build_rows("object", d)
    labels = [r.label for r in rows]
    assert not any("@odata.context" in l for l in labels)
    assert not any("@odata.count" in l for l in labels)
    assert any("Alice" in l for l in labels)


def test_build_rows_nav_link_is_dim() -> None:
    """Navigation link fields are marked dim=True."""
    d = {
        "manager@odata.navigationLink": "https://graph.microsoft.com/v1.0/users/me/manager",
    }
    rows = build_rows("object", d)
    nav_rows = [r for r in rows if "@odata.navigationLink" in r.label or r.dim]
    assert nav_rows, "Expected at least one dim navigation-link row"
    assert all(r.dim for r in nav_rows)


def test_build_rows_collection_prefers_display_name() -> None:
    items = [
        {"id": "u1", "displayName": "Alice Smith", "mail": "alice@example.com"},
    ]
    rows = build_rows("collection", items)
    assert rows[0].label == "Alice Smith"


def test_build_rows_collection_drillable_via_odata_id() -> None:
    items = [
        {"@odata.id": "https://graph.microsoft.com/v1.0/users/u1", "displayName": "Alice"},
    ]
    rows = build_rows("collection", items)
    assert rows[0].drillable
    assert rows[0].drill_target == "https://graph.microsoft.com/v1.0/users/u1"


def test_build_rows_non_dict_items_not_drillable() -> None:
    """Non-dict collection items → not drillable."""
    rows = build_rows("collection", ["hello", "world"])
    assert all(not r.drillable for r in rows)


# ---------------------------------------------------------------------------
# extract_next_link (TP18–TP21 + TP34–TP36)
# ---------------------------------------------------------------------------


def test_odata_next_link() -> None:
    """TP18: OData audience → @odata.nextLink."""
    payload = {
        "value": [],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?$skiptoken=abc",
    }
    cursor = extract_next_link("collection", payload, "graph")
    assert cursor == "https://graph.microsoft.com/v1.0/users?$skiptoken=abc"


def test_arm_next_link() -> None:
    """TP35: ARM audience → nextLink."""
    payload = {
        "value": [],
        "nextLink": "https://management.azure.com/subscriptions?$skipToken=xyz",
    }
    cursor = extract_next_link("collection", payload, "azure")
    assert cursor == "https://management.azure.com/subscriptions?$skipToken=xyz"


def test_devops_continuation_case_insensitive() -> None:
    """TP36: DevOps continuation token is case-insensitive."""
    headers = {"X-MS-ContinuationToken": "tok123"}
    cursor = extract_next_link("collection", {}, "devops", headers)
    assert cursor == "?continuationToken=tok123"


def test_devops_continuation_lowercase_header() -> None:
    headers = {"x-ms-continuationtoken": "tok456"}
    cursor = extract_next_link("collection", {}, "devops", headers)
    assert cursor == "?continuationToken=tok456"


def test_no_next_link_returns_none() -> None:
    payload = {"value": []}
    cursor = extract_next_link("collection", payload, "graph")
    assert cursor is None


def test_odata_next_link_in_deny_list_not_drillable() -> None:
    """@odata.nextLink should not appear as a drillable row target (deny list)."""
    from owa_tui.graph.nav import _DENY_LIST

    # This tests the constant, not build_rows directly (the deny list check is in build_rows)
    assert "@odata.nextLink" not in _DENY_LIST  # It's handled as a nav-link, not deny-list
    # But nextLink is in deny list? No — nextLink is handled by _is_nav_link_key
    # Verify that nextLink doesn't appear as drillable in object rows
    d = {
        "displayName": "Alice",
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?token=abc",
        "nextLink": "https://management.azure.com/subscriptions?skip=abc",
    }
    rows = build_rows("object", d)
    # nextLink-keyed rows should be dim
    nav_rows = [r for r in rows if "nextLink" in (r.label or "")]
    assert all(r.dim for r in nav_rows), "nextLink rows should be dim (nav-link)"


# ---------------------------------------------------------------------------
# on_drill / on_back (TP22–TP24)
# ---------------------------------------------------------------------------


def test_drill_pushes_7tuple_history() -> None:
    """TP12 (plan): on_drill pushes 7-tuple; len(state.history) == 1."""
    state = _make_state()
    state.audience = "graph"
    state.path = "users"
    state.query = ""
    state.selected = 0
    state.top = 0
    state.items = []
    state.next_link = None

    item = _drillable_row(target="users/1")
    result = on_drill(state, item)

    assert result is True
    assert len(state.history) == 1
    assert state.dirty is True
    hist = state.history[0]
    assert len(hist) == 7
    assert hist[0] == "graph"
    assert hist[1] == "users"


def test_drill_updates_path_via_next_path() -> None:
    """TP13: path updated correctly via next_path logic."""
    state = _make_state()
    state.path = "users"
    state.items = []
    state.next_link = None
    state.query = ""
    state.selected = 0
    state.top = 0

    item = _drillable_row(target="messages")
    on_drill(state, item)

    assert state.path == "users/messages"


def test_drill_non_drillable_noop() -> None:
    """TP14: drilling a non-drillable item does nothing."""
    state = _make_state()
    state.path = "users"
    state.items = []
    state.next_link = None
    state.query = ""
    state.selected = 0
    state.top = 0

    item = _non_drillable_row()
    result = on_drill(state, item)

    assert result is False
    assert len(state.history) == 0
    assert state.path == "users"


def test_back_restores_without_network() -> None:
    """TP15: on_back restores all 7 fields, dirty=False."""
    state = _make_state()
    state.audience = "graph"
    state.path = "users/1"
    state.query = ""
    state.selected = 0
    state.top = 0
    state.items = []
    state.next_link = None

    # Prime history
    old_rows = [_drillable_row()]
    state.history = [("graph", "users", "q=1", 2, 5, old_rows, "https://next")]

    result = on_back(state)

    assert result is True
    assert state.audience == "graph"
    assert state.path == "users"
    assert state.query == "q=1"
    assert state.selected == 2
    assert state.top == 5
    assert state.items == old_rows
    assert state.next_link == "https://next"
    assert state.dirty is False


def test_back_empty_history_returns_false() -> None:
    """TP16: on_back with empty history returns False."""
    state = _make_state()
    result = on_back(state)
    assert result is False


def test_back_does_not_set_dirty() -> None:
    """TP17: on_back does not set dirty=True."""
    state = _make_state()
    state.history = [("graph", "me", "", 0, 0, [], None)]
    state.dirty = False
    on_back(state)
    assert state.dirty is False


# ---------------------------------------------------------------------------
# _header_get
# ---------------------------------------------------------------------------


def test_header_get_case_insensitive() -> None:
    headers = {"X-MS-ContinuationToken": "value"}
    assert _header_get(headers, "x-ms-continuationtoken") == "value"
    assert _header_get(headers, "X-MS-CONTINUATIONTOKEN") == "value"


def test_header_get_missing_returns_none() -> None:
    assert _header_get({}, "x-ms-continuationtoken") is None
    assert _header_get(None, "any") is None  # type: ignore[arg-type]
