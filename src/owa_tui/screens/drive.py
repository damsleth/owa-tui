"""drive.py — DriveScreen: OneDrive / Microsoft 365 file-browser TUI.

Subclasses OwaTreeScreen (base screen) — the first production consumer of
the hierarchical tree base. Supplies all required hooks; all list / detail /
search / breadcrumb / menu / nav UX is inherited from the base.

v1 scope: read-only navigation (list children, drill into folders, go up,
show file detail). Upload / download / delete are deferred to v2.
"""

from __future__ import annotations

import re
from typing import Any

from owa_tui.screens.base import OwaTreeScreen, TreeNode
from owa_tui.screens.base.keys import LIST_BINDINGS

# Graph base URL — mirrors owa_drive.auth.API_BASE exactly.
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Root TreeNode: the root of OneDrive.
_ROOT_NODE = TreeNode(id="", label="OneDrive")


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------


def _fmt_size(size: int | None) -> str:
    """Format a byte count as a human-readable string."""
    if size is None:
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    if size < 1024**3:
        return f"{size / 1024**2:.1f} MB"
    return f"{size / 1024**3:.1f} GB"


def _slug(path: str) -> str:
    """Derive a fixture key slug from a folder path.

    Non-alphanumeric runs become underscores; the result is stripped of
    leading/trailing underscores.  Empty path → ``"root"`` (never used as a
    key directly — the caller uses ``"drive"`` for root).
    """
    return re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_") or "root"


def _row_text(item: dict, width: int = 80) -> str:
    """Format a single driveItem for the list row."""
    kind = item.get("kind", "unknown")
    name = item.get("name") or "(unnamed)"
    icon = "\U0001f4c1" if kind == "folder" else "\U0001f4c4"

    if kind == "folder":
        child_count = item.get("childCount")
        size_str = f"{child_count} items" if child_count is not None else "—"
    else:
        size_str = _fmt_size(item.get("size"))

    # Right column: size / child-count, right-justified in 14 chars.
    right = size_str
    # Name column: pad to fill available space.
    name_width = max(10, width - 4 - len(right) - 3)
    if len(name) > name_width:
        name = name[: name_width - 1] + "…"
    gap = max(1, width - 4 - len(name) - len(right))
    return f"{icon}  {name}{' ' * gap}{right}"


def _detail_text(item: dict) -> str:
    """Render a driveItem dict as a plain-text detail view."""
    lines: list[str] = []
    lines.append(f"Name:     {item.get('name') or '(unnamed)'}")
    lines.append(f"Kind:     {item.get('kind') or 'unknown'}")
    lines.append(f"Size:     {_fmt_size(item.get('size'))}")

    if item.get("lastModified"):
        lines.append(f"Modified: {item['lastModified']}")

    mime = item.get("mimeType") or ""
    if mime:
        lines.append(f"MIME:     {mime}")

    child_count = item.get("childCount")
    if child_count is not None:
        lines.append(f"Children: {child_count}")

    if item.get("webUrl"):
        lines.append(f"URL:      {item['webUrl']}")

    if item.get("parentPath"):
        lines.append(f"Parent:   {item['parentPath']}")

    if item.get("id"):
        lines.append(f"ID:       {item['id']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DriveScreen
# ---------------------------------------------------------------------------


class DriveScreen(OwaTreeScreen):
    """OneDrive file-browser: folders drill in, files show detail.

    Constructor keyword arguments are passed through to ``OwaTreeScreen``
    (which forwards ``**kw`` to ``OwaListScreen``).  Callers should NOT pass
    ``root_node`` — it is fixed to the OneDrive root here.

    Parameters
    ----------
    config:
        owa-core config dict (passed to ``access_token_for``).
    tool_name:
        Tool name for token minting (default ``"owa-drive"``).
    audience:
        Auth audience (default ``"graph"``).
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
        tool_name: str = "owa-drive",
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
        """Return driveItems for *node*'s path, filtered by *search*.

        Short-circuits to the fixture layer when ``OWA_TUI_FIXTURES`` is set.
        Falls back to the live Graph API otherwise.
        """
        from owa_tui import fixtures  # noqa: PLC0415

        path = node.id  # "" = drive root, "Documents/Q1 Reports" = subfolder

        # --- Fixture seam ---
        key = "drive" if not path else f"drive_{_slug(path)}"
        raw = fixtures.load(key)
        if raw is None:
            raw = fixtures.load("drive")  # always fall back to root fixture

        # --- Live API call (blocking — called from worker thread) ---
        if raw is None:
            from owa_drive.api import api_request  # type: ignore[import]  # noqa: PLC0415
            from owa_drive.paths import (  # type: ignore[import]  # noqa: PLC0415
                children_endpoint,
            )

            from owa_tui.adapter import access_token_for  # noqa: PLC0415

            if not self._token:
                self._token = access_token_for(
                    self._config, tool_name=self._tool_name, audience=self._audience
                )
            endpoint = children_endpoint(path)
            raw = api_request("GET", _GRAPH_BASE, endpoint, self._token)

        if raw is None:
            return []

        from owa_drive.items import normalize_item  # type: ignore[import]  # noqa: PLC0415

        items = [normalize_item(entry) for entry in (raw.get("value") or [])]

        # Apply search filter (case-insensitive substring on name).
        if search:
            lsearch = search.lower()
            items = [i for i in items if lsearch in (i.get("name") or "").lower()]

        return items

    def is_container(self, item: dict) -> bool:
        """True for folders (drill in), False for files (show detail)."""
        return item.get("kind") == "folder"

    def child_node(self, item: dict) -> TreeNode:
        """Build the child ``TreeNode`` to push when entering a folder."""
        parent = (item.get("parentPath") or "/").strip("/")
        name = item.get("name") or ""
        path = f"{parent}/{name}".lstrip("/") if parent else name
        return TreeNode(id=path, label=name)

    # ------------------------------------------------------------------
    # OwaListScreen abstract hooks
    # ------------------------------------------------------------------

    def render_row(self, item: dict, width: int) -> str:
        return _row_text(item, width)

    def render_detail(self, item: dict) -> str:
        return _detail_text(item)

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return (
            "OneDrive — settings",
            [],
        )

    def help_text(self) -> str:
        return "j/k move  l open/drill  h back  / search  r refresh  q quit"
