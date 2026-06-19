"""sites.py — SitesScreen: SharePoint Sites / Lists browser TUI.

Subclasses OwaTreeScreen (base screen) — the second production consumer of
the hierarchical tree base, cloned from DriveScreen. Supplies all required
hooks; all list / detail / search / breadcrumb / menu / nav UX is inherited
from the base.

Two-level read-only tree (v1):
  root (id="")      -> SharePoint lists for the configured site
  drilled (id=title)-> Items inside that list

Upload / edit / delete and multi-site selection are deferred to v2.
"""

from __future__ import annotations

import re
from typing import Any

from owa_tui.screens.base import OwaTreeScreen, TreeNode
from owa_tui.screens.base.keys import LIST_BINDINGS

# Root TreeNode: the entry point for the SharePoint site's lists.
_ROOT_NODE = TreeNode(id="", label="SharePoint Sites")


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------


def _slug(path: str) -> str:
    """Derive a fixture key slug from a list title.

    Non-alphanumeric runs become underscores; the result is stripped of
    leading/trailing underscores.  Empty path → ``"root"`` (never used as a
    key directly — the caller uses ``"sites"`` for root).
    """
    return re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_") or "root"


def _row_text(item: dict, width: int = 80) -> str:
    """Format a single SharePoint list or item for the list row."""
    kind = item.get("_kind", "item")
    if kind == "list":
        icon = "\U0001f4cb"  # clipboard = SharePoint list
        title = item.get("title") or "(unnamed)"
        count = item.get("itemCount")
        right = f"{count} items" if count is not None else "—"
    else:
        icon = "\U0001f4c4"  # document = list item
        title = (
            item.get("Title")
            or item.get("FileLeafRef")
            or str(item.get("Id", "(unnamed)"))
        )
        right = item.get("Modified", "—")[:10] if item.get("Modified") else "—"

    name_width = max(10, width - 4 - len(right) - 3)
    if len(title) > name_width:
        title = title[: name_width - 1] + "…"
    gap = max(1, width - 4 - len(title) - len(right))
    return f"{icon}  {title}{' ' * gap}{right}"


def _detail_text(item: dict) -> str:
    """Render a SharePoint list or item dict as a plain-text detail view."""
    kind = item.get("_kind", "item")
    lines: list[str] = []

    if kind == "list":
        lines.append(f"Title:     {item.get('title') or '(unnamed)'}")
        lines.append("Kind:      list")
        count = item.get("itemCount")
        if count is not None:
            lines.append(f"Items:     {count}")
        tmpl = item.get("baseTemplate")
        if tmpl is not None:
            lines.append(f"Template:  {tmpl}")
        if item.get("id"):
            lines.append(f"ID:        {item['id']}")
    else:
        # List item — render the non-internal keys as a key-value table.
        title = (
            item.get("Title")
            or item.get("FileLeafRef")
            or str(item.get("Id", "(unnamed)"))
        )
        lines.append(f"Title:     {title}")
        lines.append("Kind:      item")
        # Render all remaining fields except internal marker.
        skip = {"_kind", "Title"}
        for key, val in item.items():
            if key in skip or val is None:
                continue
            lines.append(f"{key}:".ljust(11) + f" {val}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SitesScreen
# ---------------------------------------------------------------------------


class SitesScreen(OwaTreeScreen):
    """SharePoint Lists browser: lists are drillable, items show detail.

    Constructor keyword arguments are passed through to ``OwaTreeScreen``
    (which forwards ``**kw`` to ``OwaListScreen``).  Callers should NOT pass
    ``root_node`` — it is fixed to the SharePoint root here.

    Parameters
    ----------
    config:
        owa-core config dict (passed to auth helpers).
    tool_name:
        Tool name for token minting (default ``"owa-sites"``).
    audience:
        Auth audience (default ``"graph"`` — owa-sites uses a graph token
        with a per-tenant SharePoint scope override via ``setup_auth``).
    detail_pane_mode:
        ``"right"`` (default), ``"full"``, or ``"off"``.
    debug:
        Enable verbose logging.
    initial_items:
        Pre-loaded items for tests / fixture mode — skip the first fetch.
    """

    BINDINGS = LIST_BINDINGS  # type: ignore[assignment]

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        tool_name: str = "owa-sites",
        audience: str = "graph",
        detail_pane_mode: str = "right",
        debug: bool = False,
        initial_items: list[dict] | None = None,
        **kw: Any,
    ) -> None:
        self._config = config or {}
        self._tool_name = tool_name
        self._audience = audience
        self._token: str = ""
        self._sp_base: str = ""
        super().__init__(
            root_node=_ROOT_NODE,
            tool_name=tool_name,
            audience=audience,
            detail_pane_mode=detail_pane_mode,
            debug=debug,
            initial_items=initial_items,
            **kw,
        )

    # ------------------------------------------------------------------
    # OwaTreeScreen abstract hooks
    # ------------------------------------------------------------------

    async def load_node(self, node: TreeNode, search: str) -> list[dict]:
        """Return SharePoint lists (root) or list items (drilled), filtered by search.

        Short-circuits to the fixture layer when ``OWA_TUI_FIXTURES`` is set.
        Falls back to the live SharePoint REST API otherwise.
        """
        from owa_tui import fixtures  # noqa: PLC0415

        path = node.id  # "" = root (lists), "Project Tracker" = list title

        # --- Fixture seam ---
        # Track whether we fell back to the root fixture so normalization
        # uses the correct shape (list vs. item).
        effective_path = path
        key = "sites" if not path else f"sites_{_slug(path)}"
        raw = fixtures.load(key)
        if raw is None:
            raw = fixtures.load("sites")  # always fall back to root fixture
            if raw is not None:
                effective_path = ""  # root fallback → normalize as lists

        # --- Live API call (blocking — called from worker thread) ---
        if raw is None:
            from owa_sites.api import paginate_sp  # type: ignore[import]  # noqa: PLC0415
            from owa_sites.auth import setup_auth  # type: ignore[import]  # noqa: PLC0415
            from owa_sites.config import load_config  # type: ignore[import]  # noqa: PLC0415
            from owa_sites.sites import (  # type: ignore[import]  # noqa: PLC0415
                list_items_endpoint,
                lists_endpoint,
            )

            if not self._token or not self._sp_base:
                cfg = {**load_config(), **self._config}
                self._token, self._sp_base = setup_auth(cfg, debug=False)

            site = self._config.get("default_site") or ""
            if not path:
                endpoint = lists_endpoint(site)
                raw_list = paginate_sp(self._sp_base, endpoint, self._token)
            else:
                endpoint = list_items_endpoint(site, path)
                raw_list = paginate_sp(self._sp_base, endpoint, self._token)

            # paginate_sp returns a plain list (already merged pages)
            raw = {"value": raw_list or []}

        if raw is None:
            return []

        # Normalize via owa_sites.sites helpers
        from owa_sites.sites import (  # type: ignore[import]  # noqa: PLC0415
            normalize_items,
            normalize_lists,
        )

        if not effective_path:
            # Root (or fell back to root fixture): normalize as lists and tag kind
            rows = normalize_lists(raw, include_hidden=False)
            for row in rows:
                row["_kind"] = "list"
        else:
            # Drilled: normalize as items and tag kind
            rows = normalize_items(raw)
            for row in rows:
                row["_kind"] = "item"

        # Apply search filter (case-insensitive substring on display name).
        if search:
            lsearch = search.lower()
            rows = [
                r
                for r in rows
                if lsearch
                in (
                    r.get("title")
                    or r.get("Title")
                    or r.get("FileLeafRef")
                    or str(r.get("Id", ""))
                ).lower()
            ]

        return rows

    def is_container(self, item: dict) -> bool:
        """True for lists (drill in), False for items (show detail)."""
        return item.get("_kind") == "list"

    def child_node(self, item: dict) -> TreeNode:
        """Build the child ``TreeNode`` to push when entering a list."""
        title = item.get("title") or ""
        return TreeNode(id=title, label=title)

    # ------------------------------------------------------------------
    # OwaListScreen abstract hooks
    # ------------------------------------------------------------------

    def render_row(self, item: dict, width: int) -> str:
        return _row_text(item, width)

    def render_detail(self, item: dict) -> str:
        return _detail_text(item)

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return (
            "SharePoint Sites — settings",
            [],
        )

    def help_text(self) -> str:
        return "j/k move  l open/drill  h back  / search  r refresh  q quit"
