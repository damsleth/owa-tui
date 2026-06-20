"""Unit and Pilot tests for TodoScreen.

Coverage targets:
- _row_text / _detail_text pure helpers (no Textual)
- TodoScreen.fetch_items with fixture + search filter paths
- TodoScreen pilot: list renders, j+l opens detail, h closes, c toggles,
  menu, refresh, empty result, search, error status.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.todo import TodoScreen, _detail_text, _row_text

# ---------------------------------------------------------------------------
# Sample task dicts (already normalized — same shape normalize_task returns)
# ---------------------------------------------------------------------------


def _tasks(n: int = 3) -> list[dict]:
    statuses = ["NotStarted", "InProgress", "Completed"]
    return [
        {
            "id": f"task-{i:03d}",
            "subject": f"Task {i}",
            "status": statuses[i % len(statuses)],
            "importance": "Normal" if i % 3 != 0 else "High",
            "due": f"2026-06-{20 + i:02d}" if i % 2 == 0 else "",
            "start": "",
            "completed": "",
            "reminder": "",
            "categories": ["Cat"] if i % 3 == 0 else [],
            "folderId": "folder-001",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Helpers: app factory
# ---------------------------------------------------------------------------


def _make_app(**screen_kw: Any) -> App:
    """Return a Textual App that pushes a TodoScreen on mount."""

    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(TodoScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Pure helper tests — no Textual app needed
# ---------------------------------------------------------------------------


def test_row_text_no_due_no_cats() -> None:
    task = {"subject": "Buy milk", "status": "NotStarted", "importance": "Normal", "due": "", "categories": []}
    row = _row_text(task, width=80)
    assert "Buy milk" in row
    assert "[ ]" in row


def test_row_text_completed_shows_x() -> None:
    task = {"subject": "Done thing", "status": "Completed", "importance": "Normal", "due": "", "categories": []}
    row = _row_text(task, width=80)
    assert "[x]" in row


def test_row_text_high_importance() -> None:
    task = {"subject": "Urgent", "status": "NotStarted", "importance": "High", "due": "", "categories": []}
    row = _row_text(task, width=80)
    assert "!" in row


def test_row_text_with_due_and_cats() -> None:
    task = {
        "subject": "Report",
        "status": "InProgress",
        "importance": "Normal",
        "due": "2026-06-20",
        "categories": ["Work"],
    }
    row = _row_text(task, width=100)
    assert "due 2026-06-20" in row
    assert "[Work]" in row


def test_row_text_truncates_long_subject() -> None:
    task = {"subject": "X" * 200, "status": "NotStarted", "importance": "Normal", "due": "", "categories": []}
    row = _row_text(task, width=50)
    assert len(row) <= 60  # some tolerance for the prefix


def test_row_text_low_importance_dot() -> None:
    task = {"subject": "Low task", "status": "NotStarted", "importance": "Low", "due": "", "categories": []}
    row = _row_text(task, width=80)
    assert "·" in row


def test_row_text_in_progress_tilde() -> None:
    task = {"subject": "In flight", "status": "InProgress", "importance": "Normal", "due": "", "categories": []}
    row = _row_text(task, width=80)
    assert "[~]" in row


def test_row_text_waiting_question() -> None:
    task = {"subject": "Waiting", "status": "WaitingOnOthers", "importance": "Normal", "due": "", "categories": []}
    row = _row_text(task, width=80)
    assert "[?]" in row


def test_row_text_deferred_dash() -> None:
    task = {"subject": "Deferred", "status": "Deferred", "importance": "Normal", "due": "", "categories": []}
    row = _row_text(task, width=80)
    assert "[-]" in row


def test_row_text_empty_subject() -> None:
    row = _row_text({}, width=80)
    assert "(no title)" in row


def test_detail_text_full() -> None:
    task = {
        "subject": "Review doc",
        "status": "InProgress",
        "importance": "High",
        "due": "2026-06-20",
        "start": "2026-06-18",
        "completed": "",
        "reminder": "2026-06-19T09:00:00",
        "categories": ["Work", "Docs"],
        "folderId": "folder-001",
    }
    detail = _detail_text(task)
    assert "Review doc" in detail
    assert "InProgress" in detail
    assert "High" in detail
    assert "due" in detail.lower() or "2026-06-20" in detail
    assert "2026-06-18" in detail
    assert "2026-06-19T09:00:00" in detail
    assert "Work" in detail
    assert "folder-001" in detail


def test_detail_text_minimal() -> None:
    detail = _detail_text({"subject": "Simple task"})
    assert "Simple task" in detail


def test_detail_text_empty_task() -> None:
    detail = _detail_text({})
    assert "(no title)" in detail


def test_detail_text_completed_field() -> None:
    task = {
        "subject": "Done",
        "status": "Completed",
        "importance": "Normal",
        "completed": "2026-06-15",
        "due": "",
        "start": "",
        "reminder": "",
        "categories": [],
        "folderId": "",
    }
    detail = _detail_text(task)
    assert "2026-06-15" in detail


# ---------------------------------------------------------------------------
# Pilot tests — TodoScreen with preloaded items
# ---------------------------------------------------------------------------


def test_list_renders_tasks() -> None:
    async def _run() -> bool:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            # At least one Task row should be in the DOM
            items = app.screen._items
            return len(items) == 3

    assert asyncio.run(_run())


def test_j_moves_cursor_down() -> None:
    async def _run() -> int:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.pause(0.05)
            return app.screen._selected_idx

    # With preloaded items the list starts at index 0 already selected;
    # pressing j advances to index 1.
    assert asyncio.run(_run()) == 1


def test_j_then_l_opens_detail_mode() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("l")
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "detail"


def test_h_closes_detail() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("l")
            await pilot.press("h")
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "list"


def test_detail_pane_right_mounted() -> None:
    from owa_tui.screens.base.screen import _DetailPane

    async def _run() -> int:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) >= 1


def test_detail_pane_off_not_mounted() -> None:
    from owa_tui.screens.base.screen import _DetailPane

    async def _run() -> int:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) == 0


def test_escape_opens_menu() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "SettingsOverlay"


def test_q_quits() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) != "TodoScreen"


def test_search_key_opens_modal() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_tasks(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("/")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "_SearchModal"


def test_refresh_refetches() -> None:
    """r key triggers a re-fetch."""
    items = _tasks(2)

    async def _run() -> int:
        with patch.object(TodoScreen, "fetch_items", return_value=items) as mock_fetch:
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("r")
                await pilot.pause(0.3)
                return mock_fetch.call_count

    assert asyncio.run(_run()) >= 2


# ---------------------------------------------------------------------------
# Complete-toggle action tests
# ---------------------------------------------------------------------------


def test_toggle_complete_marks_completed() -> None:
    async def _run() -> str:
        tasks = _tasks(3)
        # List starts at index 0; j advances to index 1 — set that item up.
        tasks[1]["status"] = "NotStarted"
        app = _make_app(initial_items=tasks, detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")  # move from index 0 to index 1
            await pilot.press("c")  # toggle item at index 1
            await pilot.pause(0.05)
            return app.screen._items[1]["status"]

    assert asyncio.run(_run()) == "Completed"


def test_toggle_complete_uncompletes() -> None:
    async def _run() -> str:
        tasks = _tasks(3)
        # List starts at index 0; j advances to index 1.
        tasks[1]["status"] = "Completed"
        app = _make_app(initial_items=tasks, detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")  # move to index 1
            await pilot.press("c")  # toggle
            await pilot.pause(0.05)
            return app.screen._items[1]["status"]

    assert asyncio.run(_run()) == "NotStarted"


def test_toggle_no_selection_sets_status() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=[], detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("c")
            await pilot.pause(0.05)
            return app.screen._status

    assert "no task selected" in asyncio.run(_run())


# ---------------------------------------------------------------------------
# Live (non-fixture) complete-toggle PATCH path — not reachable via e2e
# (fixture mode short-circuits in _patch_complete), so unit-test the worker.
# ---------------------------------------------------------------------------


class _SyncThread:
    """Run the worker target inline on .start() — deterministic, traceable."""

    def __init__(self, target=None, daemon=None, **_kw):
        self._target = target

    def start(self) -> None:
        if self._target is not None:
            self._target()


def test_do_patch_complete_fires_patch_with_token() -> None:
    """With a token, the worker PATCHes the task via owa_todo.api."""
    calls: list[tuple] = []

    screen = TodoScreen(config={})
    with (
        patch("threading.Thread", _SyncThread),
        patch("owa_tui.adapter.access_token_for", return_value="tok"),
        patch("owa_todo.api.api_request", side_effect=lambda *a, **k: calls.append((a, k))),
    ):
        screen._do_patch_complete("task-001", "Completed")

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "PATCH"
    assert "me/tasks/task-001" in args[2]
    assert kwargs["body"] == {"Status": "Completed"}


def test_do_patch_complete_no_token_skips_patch() -> None:
    """With no token, the worker returns early and never calls api_request."""
    called: list[int] = []

    screen = TodoScreen(config={})
    with (
        patch("threading.Thread", _SyncThread),
        patch("owa_tui.adapter.access_token_for", return_value=""),
        patch("owa_todo.api.api_request", side_effect=lambda *a, **k: called.append(1)),
    ):
        screen._do_patch_complete("task-001", "Completed")

    assert called == []


def test_do_patch_complete_swallows_errors() -> None:
    """Exceptions in the worker are caught (best-effort PATCH, never crashes)."""
    screen = TodoScreen(config={})
    with (
        patch("threading.Thread", _SyncThread),
        patch("owa_tui.adapter.access_token_for", side_effect=RuntimeError("boom")),
    ):
        screen._do_patch_complete("task-001", "Completed")  # must not raise


# ---------------------------------------------------------------------------
# fetch_items tests (async, no Textual app)
# ---------------------------------------------------------------------------


def test_fetch_items_fixture_mode() -> None:
    """fetch_items returns fixture data when OWA_TUI_FIXTURES is set."""
    import os
    import pathlib

    fixture_dir = str(pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures")

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": fixture_dir}):
            screen = TodoScreen(config={})
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 3
    subjects = [t["subject"] for t in items]
    assert "Review quarterly report" in subjects


def test_fetch_items_fixture_search_filter() -> None:
    """fetch_items filters by search term when fixtures are loaded."""
    import os
    import pathlib

    fixture_dir = str(pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures")

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": fixture_dir}):
            screen = TodoScreen(config={})
            return await screen.fetch_items(search="quarterly")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["subject"] == "Review quarterly report"


def test_fetch_items_fixture_search_no_match() -> None:
    """fetch_items returns [] when search matches nothing."""
    import os
    import pathlib

    fixture_dir = str(pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures")

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": fixture_dir}):
            screen = TodoScreen(config={})
            return await screen.fetch_items(search="xyzzy-no-match")

    items = asyncio.run(_run())
    assert items == []


def test_fetch_items_api_returns_none() -> None:
    """fetch_items returns [] when api_get returns None (no fixtures)."""

    async def _run() -> list[dict]:
        screen = TodoScreen(config={})
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_todo.api.api_get", return_value=None),
        ):
            return await screen.fetch_items()

    assert asyncio.run(_run()) == []


def test_fetch_items_api_returns_data() -> None:
    """fetch_items normalizes data from api_get."""
    raw = {
        "value": [
            {
                "Id": "t1",
                "Subject": "My task",
                "Status": "NotStarted",
                "Importance": "Normal",
                "DueDateTime": None,
                "StartDateTime": None,
                "CompletedDateTime": None,
                "IsReminderOn": False,
                "ReminderDateTime": None,
                "Categories": [],
                "ParentFolderId": "f1",
            }
        ]
    }

    async def _run() -> list[dict]:
        screen = TodoScreen(config={})
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_todo.api.api_get", return_value=raw),
        ):
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["subject"] == "My task"


# ---------------------------------------------------------------------------
# menu_config
# ---------------------------------------------------------------------------


def test_menu_config_returns_tuple() -> None:
    sc = TodoScreen()
    title, fields = sc.menu_config()
    assert isinstance(title, str)
    assert isinstance(fields, list)


# ---------------------------------------------------------------------------
# render_row / render_detail via screen methods
# ---------------------------------------------------------------------------


def test_render_row_via_screen() -> None:
    sc = TodoScreen()
    task = _tasks(1)[0]
    row = sc.render_row(task, 80)
    assert isinstance(row, str)
    assert len(row) > 0


def test_render_detail_via_screen() -> None:
    sc = TodoScreen()
    task = _tasks(1)[0]
    detail = sc.render_detail(task)
    assert isinstance(detail, str)
    assert "Task" in detail


# ---------------------------------------------------------------------------
# _patch_complete fixture-mode no-op
# ---------------------------------------------------------------------------


def test_patch_complete_noop_in_fixture_mode() -> None:
    """_patch_complete returns early without spawning a thread in fixture mode."""
    sc = TodoScreen()
    with patch("owa_tui.fixtures.enabled", return_value=True):
        with patch("threading.Thread") as mock_thread:
            sc._patch_complete("task-001", "Completed")
            mock_thread.assert_not_called()


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def test_todo_registered_in_registry() -> None:
    from owa_tui.screens import SCREEN_REGISTRY

    assert "todo" in SCREEN_REGISTRY
    assert SCREEN_REGISTRY["todo"]["label"] == "Tasks"
    assert SCREEN_REGISTRY["todo"]["screen_class"] is TodoScreen


# ---------------------------------------------------------------------------
# Worker: fetch populates list via pilot
# ---------------------------------------------------------------------------


def test_fetch_worker_populates_via_pilot() -> None:
    """Ensure the fetch worker path (no initial_items) works with mocked fetch."""
    items = _tasks(2)

    async def _run() -> int:
        with patch.object(TodoScreen, "fetch_items", return_value=items):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return len(app.screen._items)

    assert asyncio.run(_run()) == 2


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        with patch.object(TodoScreen, "fetch_items", side_effect=RuntimeError("boom")):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return app.screen._status

    assert "error: boom" in asyncio.run(_run())


# ---------------------------------------------------------------------------
# help_text
# ---------------------------------------------------------------------------


def test_help_text_contains_keys() -> None:
    sc = TodoScreen()
    ht = sc.help_text()
    assert "j" in ht or "move" in ht
    assert "c" in ht or "complete" in ht.lower()
