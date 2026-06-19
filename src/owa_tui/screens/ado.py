"""ado.py — AdoScreen: Azure DevOps work-item TUI.

Subclasses OwaListScreen — implements only the four abstract hooks.
All list/detail/search/menu machinery is inherited from the base.

v1 is read-only: no mutation bindings.
"""

from __future__ import annotations

from typing import Any

from owa_tui.screens.base import OwaListScreen
from owa_tui.screens.base.keys import LIST_BINDINGS

_STATE_ICON: dict[str, str] = {
    "New": "[ ]",
    "Active": "[~]",
    "Resolved": "[.]",
    "Closed": "[x]",
}

_PRIORITY_MARK: dict[int, str] = {
    1: "!!",
    2: "! ",
    3: "  ",
    4: "  ",
}


# ---------------------------------------------------------------------------
# Module-level pure helpers (easy to unit test without a Textual app)
# ---------------------------------------------------------------------------


def _row_text(item: dict, width: int = 80) -> str:
    """Format a single ADO work item for the list row."""
    title = item.get("title") or "(no title)"
    state = item.get("state") or "New"
    pri = item.get("priority") or 3
    wit = item.get("type") or ""
    id_ = item.get("id")

    icon = _STATE_ICON.get(state, "[ ]")
    mark = _PRIORITY_MARK.get(int(pri) if pri else 3, "  ")

    right = f"#{id_} {wit}" if id_ else wit
    prefix = f"{icon} {mark} "
    max_title = max(10, width - len(prefix) - len(right) - 3)
    if len(title) > max_title:
        title = title[: max_title - 1] + "…"

    if right:
        gap = max(1, width - len(prefix) - len(title) - len(right))
        return f"{prefix}{title}{' ' * gap}{right}"
    return f"{prefix}{title}"


def _detail_text(item: dict) -> str:
    """Render an ADO work item dict as a plain-text detail view."""
    lines: list[str] = []
    lines.append(f"Title:       {item.get('title') or '(no title)'}")

    if item.get("id"):
        lines.append(f"ID:          #{item['id']}")

    if item.get("type"):
        lines.append(f"Type:        {item['type']}")

    if item.get("state"):
        lines.append(f"State:       {item['state']}")

    if item.get("priority"):
        lines.append(f"Priority:    {item['priority']}")

    if item.get("assignedTo"):
        lines.append(f"Assigned to: {item['assignedTo']}")

    if item.get("iteration"):
        lines.append(f"Iteration:   {item['iteration']}")

    if item.get("area"):
        lines.append(f"Area:        {item['area']}")

    if item.get("tags"):
        lines.append(f"Tags:        {item['tags']}")

    if item.get("changed"):
        # Show date portion only (YYYY-MM-DD)
        changed = str(item["changed"])[:10]
        lines.append(f"Changed:     {changed}")

    if item.get("url"):
        lines.append(f"URL:         {item['url']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AdoScreen
# ---------------------------------------------------------------------------


class AdoScreen(OwaListScreen):
    """Azure DevOps work-item list screen.

    Subclasses OwaListScreen — implements only the four abstract hooks.
    All list/detail/search/menu machinery is inherited from the base.

    v1 is read-only: no mutation bindings.
    """

    BINDINGS = LIST_BINDINGS  # type: ignore[assignment]

    def __init__(self, config: dict[str, Any] | None = None, **kw: Any) -> None:
        detail_pane_mode = kw.pop("detail_pane_mode", "right")
        super().__init__(
            config=config,
            tool_name="owa-ado",
            audience="devops",
            title="Azure DevOps",
            detail_pane_mode=detail_pane_mode,
            split_ratio=kw.pop("split_ratio", 55),
            search_prompt=kw.pop("search_prompt", "Filter work items:"),
            search_placeholder=kw.pop("search_placeholder", "title keyword…"),
            empty_label=kw.pop("empty_label", "(no work items)"),
            **kw,
        )

    # -------------------------------------------------------------------------
    # Abstract hook: fetch
    # -------------------------------------------------------------------------

    async def fetch_items(self, search: str = "") -> list[dict]:
        """Fetch work items from Azure DevOps; returns normalized list.

        Uses fixture short-circuit when OWA_TUI_FIXTURES is set.
        Live path does a two-step fetch: WIQL POST for IDs, then batch GET.
        """
        from owa_tui import fixtures  # noqa: PLC0415
        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        token = access_token_for(
            self._config, tool_name=self._tool_name, audience=self._audience
        )

        # Fixture short-circuit — must be BEFORE any ado_request call
        raw = fixtures.load("ado")

        if raw is None:
            # Live two-step fetch
            from owa_ado.api import ado_request  # type: ignore[import]  # noqa: PLC0415
            from owa_ado.auth import org_base  # type: ignore[import]  # noqa: PLC0415
            from owa_ado.config import load_config  # type: ignore[import]  # noqa: PLC0415
            from owa_ado.resources import (  # type: ignore[import]  # noqa: PLC0415
                WI_FIELDS,
                build_wiql,
            )

            ado_config = load_config()
            org = ado_config.get("ado_org") or (self._config or {}).get("ado_org") or ""
            project = (
                ado_config.get("ado_project")
                or (self._config or {}).get("ado_project")
                or ""
            )
            if not org or not project:
                return []

            base = org_base(org)

            # Step 1: WIQL POST — returns only work-item IDs
            wiql_body = {"query": build_wiql(project=project, mine=True)}
            wiql = ado_request(
                "POST",
                base,
                f"{project}/_apis/wit/wiql",
                token,
                body=wiql_body,
                query={"$top": 50},
            )
            if wiql is None:
                return []

            ids = [
                str(w["id"])
                for w in (wiql.get("workItems") or [])
                if w.get("id")
            ]
            ids = ids[:50]
            if not ids:
                return []

            # Step 2: Batch GET — fetch all fields in one call
            raw = ado_request(
                "GET",
                base,
                "_apis/wit/workitems",
                token,
                query={"ids": ",".join(ids), "fields": ",".join(WI_FIELDS)},
            )

        if raw is None:
            return []

        from owa_ado.resources import (  # type: ignore[import]  # noqa: PLC0415
            normalize_work_item,
        )

        items = [normalize_work_item(w) for w in (raw.get("value") or [])]

        if search:
            lsearch = search.lower()
            items = [i for i in items if lsearch in (i.get("title") or "").lower()]

        return items

    # -------------------------------------------------------------------------
    # Abstract hook: render_row
    # -------------------------------------------------------------------------

    def render_row(self, item: dict, width: int) -> str:
        return _row_text(item, width)

    # -------------------------------------------------------------------------
    # Abstract hook: render_detail
    # -------------------------------------------------------------------------

    def render_detail(self, item: dict) -> str:
        return _detail_text(item)

    # -------------------------------------------------------------------------
    # Abstract hook: menu_config
    # -------------------------------------------------------------------------

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return (
            "Azure DevOps — settings",
            [],
        )

    # -------------------------------------------------------------------------
    # Optional: help text
    # -------------------------------------------------------------------------

    def help_text(self) -> str:
        return "j/k move  Enter open  / search  r refresh  q quit"

    # -------------------------------------------------------------------------
    # Optional: open_browser_for
    # -------------------------------------------------------------------------

    def open_browser_for(self, item: dict) -> str | None:
        return item.get("url") or None
