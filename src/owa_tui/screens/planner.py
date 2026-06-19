"""planner.py — PlannerScreen: Microsoft Planner TUI.

Subclasses OwaListScreen (base screen) — the second production consumer of
that base.  Supplies the four abstract hooks; everything else (layout, search,
Esc overlay, keybindings, status bar) is handled by the base.

v1 is read-only: no mutation bindings.
"""

from __future__ import annotations

from typing import Any

from owa_tui.screens.base import OwaListScreen
from owa_tui.screens.base.keys import LIST_BINDINGS

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_STATUS_ICON: dict[str, str] = {
    "NotStarted": "[ ]",
    "InProgress": "[~]",
    "Completed": "[x]",
}

_PRIORITY_MARK: dict[str, str] = {
    "urgent": "!!",
    "important": "! ",
    "medium": "  ",
    "low": "  ",
}


# ---------------------------------------------------------------------------
# Module-level pure helpers (easy to unit test without a Textual app)
# ---------------------------------------------------------------------------


def _row_text(task: dict, width: int = 80) -> str:
    """Format a single planner task for the list row."""
    title = task.get("title") or "(no title)"
    status = task.get("status") or "NotStarted"
    priority_label = task.get("priorityLabel") or "medium"
    due = task.get("due") or ""

    icon = _STATUS_ICON.get(status, "[ ]")
    pri = _PRIORITY_MARK.get(priority_label, "  ")

    right = f"due {due}" if due else ""
    prefix = f"{icon} {pri} "
    max_title = max(10, width - len(prefix) - len(right) - 3)
    if len(title) > max_title:
        title = title[: max_title - 1] + "…"

    if right:
        gap = max(1, width - len(prefix) - len(title) - len(right))
        return f"{prefix}{title}{' ' * gap}{right}"
    return f"{prefix}{title}"


def _detail_text(task: dict) -> str:
    """Render a planner task dict as a plain-text detail view."""
    lines: list[str] = []
    title = task.get("title") or "(no title)"
    lines.append(f"Title:    {title}")

    status = task.get("status") or ""
    pct = task.get("percentComplete", 0)
    if status:
        lines.append(f"Status:   {status} ({pct}%)")

    priority_label = task.get("priorityLabel") or ""
    if priority_label:
        lines.append(f"Priority: {priority_label}")

    due = task.get("due") or ""
    if due:
        lines.append(f"Due:      {due}")

    start = task.get("start") or ""
    if start:
        lines.append(f"Start:    {start}")

    completed = task.get("completed") or ""
    if completed:
        lines.append(f"Completed:{completed}")

    if task.get("hasDescription"):
        lines.append("(has description — fetch /details for body)")

    total = task.get("checklistItemCount") or 0
    n = task.get("activeChecklistItemCount") or 0
    if total:
        lines.append(f"Checklist:{n}/{total} open")

    plan_id = task.get("planId") or ""
    if plan_id:
        lines.append(f"Plan:     {plan_id}")

    bucket_id = task.get("bucketId") or ""
    if bucket_id:
        lines.append(f"Bucket:   {bucket_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PlannerScreen
# ---------------------------------------------------------------------------


class PlannerScreen(OwaListScreen):
    """Microsoft Planner task list screen.

    Subclasses OwaListScreen — implements only the four abstract hooks.
    All list/detail/search/menu machinery is inherited from the base.

    v1 is read-only: no mutation bindings.
    """

    BINDINGS = LIST_BINDINGS  # type: ignore[assignment]

    def __init__(self, config: dict[str, Any] | None = None, **kw: Any) -> None:
        detail_pane_mode = kw.pop("detail_pane_mode", "right")
        super().__init__(
            config=config,
            tool_name="owa-planner",
            audience="graph",
            title="Planner",
            detail_pane_mode=detail_pane_mode,
            split_ratio=kw.pop("split_ratio", 55),
            search_prompt=kw.pop("search_prompt", "Filter tasks:"),
            search_placeholder=kw.pop("search_placeholder", "title keyword…"),
            empty_label=kw.pop("empty_label", "(no tasks)"),
            **kw,
        )

    # -------------------------------------------------------------------------
    # Abstract hook: fetch
    # -------------------------------------------------------------------------

    async def fetch_items(self, search: str = "") -> list[dict]:
        """Fetch tasks from Microsoft Graph Planner; returns normalized list."""
        from owa_tui import fixtures  # noqa: PLC0415
        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        token = access_token_for(
            self._config, tool_name=self._tool_name, audience=self._audience
        )

        # Fixture short-circuit (e2e / offline mode)
        raw = fixtures.load("planner")

        if raw is None:
            # Live fetch
            from owa_planner.api import (  # type: ignore[import]  # noqa: PLC0415
                api_get,
                build_query,
            )

            endpoint = f"me/planner/tasks?{build_query({'$top': 50})}"
            raw = api_get(GRAPH_BASE, endpoint, token, debug=self._debug)

        if raw is None:
            return []

        from owa_planner.plans import normalize_tasks  # type: ignore[import]  # noqa: PLC0415

        tasks = normalize_tasks(raw)

        if search:
            lsearch = search.lower()
            tasks = [t for t in tasks if lsearch in (t.get("title") or "").lower()]

        return tasks

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
            "Planner — settings",
            [],
        )

    # -------------------------------------------------------------------------
    # Optional: help text
    # -------------------------------------------------------------------------

    def help_text(self) -> str:
        return "j/k move  Enter open  / search  r refresh  q quit"
