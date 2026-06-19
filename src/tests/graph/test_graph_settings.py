"""Tests for GraphSettings and bookmark helpers."""

from __future__ import annotations

from owa_tui.graph.settings import GraphSettings, dump_bookmarks, parse_bookmarks

# ---------------------------------------------------------------------------
# parse_bookmarks / dump_bookmarks
# ---------------------------------------------------------------------------


def test_parse_bookmarks_empty_string() -> None:
    assert parse_bookmarks("") == []


def test_parse_bookmarks_valid_json() -> None:
    raw = '[["graph", "users", "Users"], ["azure", "subscriptions", "Subscriptions"]]'
    result = parse_bookmarks(raw)
    assert result == [
        ("graph", "users", "Users"),
        ("azure", "subscriptions", "Subscriptions"),
    ]


def test_parse_bookmarks_invalid_json_returns_empty() -> None:
    assert parse_bookmarks("not json at all") == []


def test_dump_bookmarks_roundtrip() -> None:
    bookmarks = [("graph", "me", "Me"), ("azure", "subscriptions", "Subs")]
    raw = dump_bookmarks(bookmarks)
    result = parse_bookmarks(raw)
    assert result == bookmarks


# ---------------------------------------------------------------------------
# GraphSettings.from_config
# ---------------------------------------------------------------------------


def test_from_config_defaults() -> None:
    settings = GraphSettings.from_config({})
    assert settings.reading_pane is True
    assert settings.split_ratio == 60
    assert settings.pretty_json is True
    assert settings.scope_warnings is True
    assert settings.default_audience == "graph"
    assert settings.default_path == "me"


def test_from_config_reads_values() -> None:
    config = {
        "graph_tui_reading_pane": False,
        "graph_tui_split_ratio": 40,
        "graph_tui_pretty_json": False,
        "graph_tui_scope_warnings": False,
        "graph_tui_default_audience": "azure",
        "graph_tui_default_path": "subscriptions",
        "graph_tui_bookmarks": '[["graph","me","Me"]]',
    }
    settings = GraphSettings.from_config(config)
    assert settings.reading_pane is False
    assert settings.split_ratio == 40
    assert settings.default_audience == "azure"
    assert settings.default_path == "subscriptions"


def test_to_config_dict_roundtrip() -> None:
    settings = GraphSettings(
        reading_pane=False,
        split_ratio=40,
        pretty_json=False,
        scope_warnings=True,
        default_audience="azure",
        default_path="subscriptions",
    )
    d = settings.to_config_dict()
    restored = GraphSettings.from_config(d)
    assert restored.reading_pane is False
    assert restored.split_ratio == 40
    assert restored.default_audience == "azure"


# ---------------------------------------------------------------------------
# add_bookmark deduplication
# ---------------------------------------------------------------------------


def test_add_bookmark_deduplicates() -> None:
    settings = GraphSettings()
    settings.add_bookmark("graph", "users", "Users")
    settings.add_bookmark("graph", "users", "Users again")
    assert len(settings.get_bookmarks()) == 1


def test_add_bookmark_different_paths_both_kept() -> None:
    settings = GraphSettings()
    settings.add_bookmark("graph", "users", "Users")
    settings.add_bookmark("graph", "groups", "Groups")
    assert len(settings.get_bookmarks()) == 2


def test_all_7_settings_fields_cycle() -> None:
    """All 7 settings fields are present in to_config_dict."""
    settings = GraphSettings()
    d = settings.to_config_dict()
    assert "graph_tui_reading_pane" in d
    assert "graph_tui_split_ratio" in d
    assert "graph_tui_pretty_json" in d
    assert "graph_tui_scope_warnings" in d
    assert "graph_tui_default_audience" in d
    assert "graph_tui_default_path" in d
    assert "graph_tui_bookmarks" in d
