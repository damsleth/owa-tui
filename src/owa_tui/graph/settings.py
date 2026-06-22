"""Graph explorer settings dataclass.

Ported from ``owa_graph.tui_settings``.

Settings fields:
- ``reading_pane``: bool — show detail pane alongside list
- ``split_ratio``: int — split ratio percent (0-100)
- ``pretty_json``: bool — format JSON (graph audience only)
- ``scope_warnings``: bool — show audience scope warning messages
- ``default_audience``: str — starting audience
- ``default_path``: str — starting path for the default audience
- ``bookmarks``: str — JSON-encoded list of (audience, path, label) triples

No Textual imports — fully unit-testable without a running app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, ClassVar

# ---------------------------------------------------------------------------
# Bookmark helpers
# ---------------------------------------------------------------------------


def parse_bookmarks(raw: str) -> list[tuple[str, str, str]]:
    """Parse a JSON-encoded bookmarks string into a list of 3-tuples."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        result: list[tuple[str, str, str]] = []
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                result.append((str(item[0]), str(item[1]), str(item[2])))
            elif isinstance(item, dict):
                result.append((
                    str(item.get("audience", "")),
                    str(item.get("path", "")),
                    str(item.get("label", "")),
                ))
        return result
    except (json.JSONDecodeError, TypeError):
        return []


def dump_bookmarks(bookmarks: list[tuple[str, str, str]]) -> str:
    """Encode bookmarks list to a JSON string for persistence."""
    return json.dumps([list(b) for b in bookmarks])


# ---------------------------------------------------------------------------
# GraphSettings
# ---------------------------------------------------------------------------


@dataclass
class GraphSettings:
    """User-configurable settings for the graph explorer."""

    reading_pane: bool = True
    split_ratio: int = 60
    pretty_json: bool = True
    scope_warnings: bool = True
    default_audience: str = "graph"
    default_path: str = "me"
    bookmarks: str = ""  # JSON-encoded list

    # Parsed bookmarks list (transient — not serialised)
    _bookmarks_list: list[tuple[str, str, str]] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._bookmarks_list = parse_bookmarks(self.bookmarks)

    # ------------------------------------------------------------------
    # Config round-trip
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "GraphSettings":
        """Build ``GraphSettings`` from an owa-tools config dict."""

        def _bool(key: str, default: bool) -> bool:
            val = config.get(key)
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("1", "true", "yes")

        def _int(key: str, default: int) -> int:
            val = config.get(key)
            if val is None:
                return default
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        def _str(key: str, default: str) -> str:
            val = config.get(key)
            return str(val) if val is not None else default

        return cls(
            reading_pane=_bool("graph_tui_reading_pane", True),
            split_ratio=_int("graph_tui_split_ratio", 60),
            pretty_json=_bool("graph_tui_pretty_json", True),
            scope_warnings=_bool("graph_tui_scope_warnings", True),
            default_audience=_str("graph_tui_default_audience", "graph"),
            default_path=_str("graph_tui_default_path", "me"),
            bookmarks=_str("graph_tui_bookmarks", ""),
        )

    # ------------------------------------------------------------------
    # Cycling (driven by SettingsOverlay)
    # ------------------------------------------------------------------

    _SPLIT_RATIO_VALUES: ClassVar[tuple[int, ...]] = (40, 50, 60)

    def cycle(self, field: str, direction: int = 1) -> "GraphSettings":
        """Return a new ``GraphSettings`` with *field* advanced by *direction* (±1).

        Bool fields toggle; ``split_ratio`` steps through its allowed values.
        Unknown / non-cyclable fields return *self* unchanged.
        """
        from dataclasses import replace

        current = getattr(self, field, None)
        if isinstance(current, bool):
            return replace(self, **{field: not current})
        if field == "split_ratio":
            vals = self._SPLIT_RATIO_VALUES
            try:
                idx = vals.index(int(current))
            except (ValueError, TypeError):
                idx = 0
            return replace(self, **{field: vals[(idx + direction) % len(vals)]})
        return self

    def to_config_dict(self) -> dict[str, Any]:
        """Serialise settings back to a config dict for persistence."""
        return {
            "graph_tui_reading_pane": self.reading_pane,
            "graph_tui_split_ratio": self.split_ratio,
            "graph_tui_pretty_json": self.pretty_json,
            "graph_tui_scope_warnings": self.scope_warnings,
            "graph_tui_default_audience": self.default_audience,
            "graph_tui_default_path": self.default_path,
            "graph_tui_bookmarks": dump_bookmarks(self._bookmarks_list),
        }

    def get_bookmarks(self) -> list[tuple[str, str, str]]:
        """Return the parsed bookmarks list."""
        return self._bookmarks_list

    def add_bookmark(self, audience: str, path: str, label: str = "") -> None:
        """Add a bookmark, deduplicating by (audience, path)."""
        key = (audience, path)
        existing_keys = {(b[0], b[1]) for b in self._bookmarks_list}
        if key not in existing_keys:
            self._bookmarks_list.append((audience, path, label or f"{audience}:{path}"))
            self.bookmarks = dump_bookmarks(self._bookmarks_list)
