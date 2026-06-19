"""todo.py — TodoScreen: Microsoft To Do / Outlook Tasks TUI.

Subclasses OwaListScreen (base screen) — the first production consumer of
that base.  Supplies the four abstract hooks; everything else (layout, search,
Esc overlay, keybindings, status bar) is handled by the base.
"""

from __future__ import annotations

from typing import Any

from textual.binding import Binding

from owa_tui.screens.base import OwaListScreen
from owa_tui.screens.base.keys import LIST_BINDINGS

API_BASE = "https://outlook.office.com/api/v2.0"

_STATUS_ICON: dict[str, str] = {
    "NotStarted": "[ ]",
    "InProgress": "[~]",
    "Completed": "[x]",
    "WaitingOnOthers": "[?]",
    "Deferred": "[-]",
}

_IMPORTANCE_MARK: dict[str, str] = {
    "High": "!",
    "Low": "·",
    "Normal": " ",
}


# ---------------------------------------------------------------------------
# Module-level pure helpers (easy to unit test without a Textual app)
# ---------------------------------------------------------------------------


def _row_text(task: dict, width: int = 80) -> str:
    """Format a single task for the list row."""
    subject = task.get("subject") or "(no title)"
    status = task.get("status") or "NotStarted"
    importance = task.get("importance") or "Normal"
    due = task.get("due") or ""

    icon = _STATUS_ICON.get(status, "[ ]")
    imp = _IMPORTANCE_MARK.get(importance, " ")

    # Build right annotation
    right_parts = []
    if due:
        right_parts.append(f"due {due}")
    cats = task.get("categories") or []
    if cats:
        right_parts.append(f"[{', '.join(cats[:2])}]")
    right = "  ".join(right_parts)

    prefix = f"{icon} {imp} "
    max_subject = max(10, width - len(prefix) - len(right) - 4)
    if len(subject) > max_subject:
        subject = subject[: max_subject - 1] + "…"

    if right:
        gap = max(1, width - len(prefix) - len(subject) - len(right) - 1)
        return f"{prefix}{subject}{' ' * gap}{right}"
    return f"{prefix}{subject}"


def _detail_text(task: dict) -> str:
    """Render a task dict as a plain-text detail view."""
    lines: list[str] = []
    subject = task.get("subject") or "(no title)"
    lines.append(f"Subject:    {subject}")

    status = task.get("status") or ""
    if status:
        lines.append(f"Status:     {status}")

    importance = task.get("importance") or ""
    if importance:
        lines.append(f"Importance: {importance}")

    due = task.get("due") or ""
    if due:
        lines.append(f"Due:        {due}")

    start = task.get("start") or ""
    if start:
        lines.append(f"Start:      {start}")

    completed = task.get("completed") or ""
    if completed:
        lines.append(f"Completed:  {completed}")

    reminder = task.get("reminder") or ""
    if reminder:
        lines.append(f"Reminder:   {reminder}")

    cats = task.get("categories") or []
    if cats:
        lines.append(f"Categories: {', '.join(cats)}")

    folder_id = task.get("folderId") or ""
    if folder_id:
        lines.append(f"Folder:     {folder_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TodoScreen
# ---------------------------------------------------------------------------


class TodoScreen(OwaListScreen):
    """Outlook Tasks / Microsoft To Do list screen.

    Subclasses OwaListScreen — implements only the four abstract hooks plus
    a complete-toggle binding.  All list/detail/search/menu machinery is
    inherited from the base.
    """

    BINDINGS = LIST_BINDINGS + [  # type: ignore[assignment]
        Binding("c", "toggle_complete", "Complete", show=True),
    ]

    def __init__(self, config: dict[str, Any] | None = None, **kw: Any) -> None:
        # Pop any args that TodoScreen hard-codes so callers (tests) can still
        # pass them without triggering "multiple values for keyword argument".
        detail_pane_mode = kw.pop("detail_pane_mode", "right")
        super().__init__(
            config=config,
            tool_name="owa-todo",
            audience="outlook",
            title="Tasks",
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
        """Fetch tasks from Outlook REST; returns normalized list of dicts."""
        from owa_tui import fixtures  # noqa: PLC0415
        from owa_tui.adapter import access_token_for  # noqa: PLC0415

        token = access_token_for(
            self._config, tool_name=self._tool_name, audience=self._audience
        )

        # Fixture short-circuit (e2e / offline mode)
        raw = fixtures.load("todo")

        if raw is None:
            # Live fetch
            from owa_todo.api import api_get, build_query  # type: ignore[import]  # noqa: PLC0415

            endpoint = f"me/tasks?{build_query({'$top': 50})}"
            raw = api_get(API_BASE, endpoint, token, debug=self._debug)

        if raw is None:
            return []

        from owa_todo.tasks import normalize_tasks  # type: ignore[import]  # noqa: PLC0415

        tasks = normalize_tasks(raw)

        if search:
            lsearch = search.lower()
            tasks = [t for t in tasks if lsearch in (t.get("subject") or "").lower()]

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
            "Tasks — settings",
            [],
        )

    # -------------------------------------------------------------------------
    # Extra action: complete-toggle
    # -------------------------------------------------------------------------

    def action_toggle_complete(self) -> None:
        """Toggle the selected task between NotStarted and Completed."""
        item = self._current_item()
        if item is None:
            self._status = "no task selected"
            return

        current_status = item.get("status") or "NotStarted"
        new_status = "Completed" if current_status != "Completed" else "NotStarted"
        task_id = item.get("id") or ""

        # Optimistic local update
        item["status"] = new_status
        self._refresh_list()

        # Persist to API in the background (no-op in fixture mode)
        if task_id:
            self._patch_complete(task_id, new_status)

    # -------------------------------------------------------------------------
    # Background PATCH worker
    # -------------------------------------------------------------------------

    def _patch_complete(self, task_id: str, new_status: str) -> None:
        """Dispatch a PATCH in a background thread (no-op in fixture mode)."""
        from owa_tui import fixtures  # noqa: PLC0415

        if fixtures.enabled():
            return

        self._do_patch_complete(task_id, new_status)

    def _do_patch_complete(self, task_id: str, new_status: str) -> None:
        """Fire a background thread to PATCH task status via Outlook REST."""
        import threading  # noqa: PLC0415
        import urllib.parse  # noqa: PLC0415

        config = self._config
        tool_name = self._tool_name
        audience = self._audience
        debug = self._debug

        def _run() -> None:
            try:
                from owa_todo.api import api_request  # type: ignore[import]  # noqa: PLC0415

                from owa_tui.adapter import access_token_for  # noqa: PLC0415

                token = access_token_for(config, tool_name=tool_name, audience=audience)
                if not token:
                    return
                endpoint = f"me/tasks/{urllib.parse.quote(task_id, safe='')}"
                api_request("PATCH", API_BASE, endpoint, token, body={"Status": new_status}, debug=debug)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    # -------------------------------------------------------------------------
    # Optional: help text
    # -------------------------------------------------------------------------

    def help_text(self) -> str:
        return (
            "j/k move  Enter open  c complete-toggle  / search  r refresh  q quit"
        )
