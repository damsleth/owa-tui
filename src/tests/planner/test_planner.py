"""Unit and Pilot tests for PlannerScreen.

Coverage targets:
- _row_text / _detail_text pure helpers (no Textual)
- PlannerScreen.fetch_items with fixture + search filter paths
- PlannerScreen pilot: list renders, j+l opens detail, h closes,
  menu, refresh, empty result, search, error status.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.planner import PlannerScreen, _detail_text, _row_text

# ---------------------------------------------------------------------------
# Sample task dicts (already normalized — same shape normalize_task returns)
# ---------------------------------------------------------------------------


def _tasks(n: int = 3) -> list[dict]:
    statuses = ["NotStarted", "InProgress", "Completed"]
    priorities = ["urgent", "important", "medium"]
    return [
        {
            "id": f"plan-task-{i:03d}",
            "title": f"Planner Task {i}",
            "status": statuses[i % len(statuses)],
            "percentComplete": [0, 50, 100][i % 3],
            "priorityLabel": priorities[i % len(priorities)],
            "due": f"2026-06-{20 + i:02d}" if i % 2 == 0 else "",
            "start": "",
            "completed": "",
            "created": "2026-06-01",
            "planId": "plan-aaa",
            "bucketId": f"bucket-{i:03d}",
            "assignedTo": [],
            "checklistItemCount": i,
            "activeChecklistItemCount": max(0, i - 1),
            "hasDescription": i % 2 == 0,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Helpers: app factory
# ---------------------------------------------------------------------------


def _make_app(**screen_kw: Any) -> App:
    """Return a Textual App that pushes a PlannerScreen on mount."""

    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(PlannerScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Pure helper tests — no Textual app needed
# ---------------------------------------------------------------------------


def test_row_text_not_started_shows_empty_box() -> None:
    task = {"title": "Todo item", "status": "NotStarted", "priorityLabel": "medium", "due": ""}
    row = _row_text(task, width=80)
    assert "[ ]" in row
    assert "Todo item" in row


def test_row_text_completed_shows_x() -> None:
    task = {"title": "Done thing", "status": "Completed", "priorityLabel": "medium", "due": ""}
    row = _row_text(task, width=80)
    assert "[x]" in row


def test_row_text_in_progress_tilde() -> None:
    task = {"title": "In flight", "status": "InProgress", "priorityLabel": "medium", "due": ""}
    row = _row_text(task, width=80)
    assert "[~]" in row


def test_row_text_urgent_priority() -> None:
    task = {"title": "Urgent", "status": "NotStarted", "priorityLabel": "urgent", "due": ""}
    row = _row_text(task, width=80)
    assert "!!" in row


def test_row_text_important_priority() -> None:
    task = {"title": "Important", "status": "NotStarted", "priorityLabel": "important", "due": ""}
    row = _row_text(task, width=80)
    assert "! " in row


def test_row_text_with_due() -> None:
    task = {
        "title": "Has due date",
        "status": "NotStarted",
        "priorityLabel": "medium",
        "due": "2026-06-25",
    }
    row = _row_text(task, width=100)
    assert "due 2026-06-25" in row


def test_row_text_truncates_long_title() -> None:
    task = {"title": "X" * 200, "status": "NotStarted", "priorityLabel": "medium", "due": ""}
    row = _row_text(task, width=50)
    assert len(row) <= 60  # tolerance for the prefix


def test_row_text_empty_title() -> None:
    row = _row_text({}, width=80)
    assert "(no title)" in row


def test_detail_text_full() -> None:
    task = {
        "title": "Review doc",
        "status": "InProgress",
        "percentComplete": 50,
        "priorityLabel": "important",
        "due": "2026-06-20",
        "start": "2026-06-18",
        "completed": "",
        "planId": "plan-aaa",
        "bucketId": "bucket-x1",
        "checklistItemCount": 3,
        "activeChecklistItemCount": 2,
        "hasDescription": True,
    }
    detail = _detail_text(task)
    assert "Review doc" in detail
    assert "InProgress" in detail
    assert "50%" in detail
    assert "important" in detail
    assert "2026-06-20" in detail
    assert "2026-06-18" in detail
    assert "has description" in detail.lower()
    assert "2/3" in detail
    assert "plan-aaa" in detail
    assert "bucket-x1" in detail


def test_detail_text_minimal() -> None:
    detail = _detail_text({"title": "Simple task"})
    assert "Simple task" in detail


def test_detail_text_empty_task() -> None:
    detail = _detail_text({})
    assert "(no title)" in detail


def test_detail_text_completed_field() -> None:
    task = {
        "title": "Done",
        "status": "Completed",
        "percentComplete": 100,
        "priorityLabel": "medium",
        "completed": "2026-06-15",
        "due": "",
        "start": "",
        "planId": "",
        "bucketId": "",
        "checklistItemCount": 0,
        "activeChecklistItemCount": 0,
        "hasDescription": False,
    }
    detail = _detail_text(task)
    assert "2026-06-15" in detail


def test_detail_text_no_checklist_no_checklist_line() -> None:
    task = {"title": "No checklist", "checklistItemCount": 0, "activeChecklistItemCount": 0}
    detail = _detail_text(task)
    assert "Checklist" not in detail


# ---------------------------------------------------------------------------
# Pilot tests — PlannerScreen with preloaded items
# ---------------------------------------------------------------------------


def test_list_renders_tasks() -> None:
    async def _run() -> bool:
        app = _make_app(initial_items=_tasks(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
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

    assert asyncio.run(_run()) != "PlannerScreen"


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
        with patch.object(PlannerScreen, "fetch_items", return_value=items) as mock_fetch:
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("r")
                await pilot.pause(0.3)
                return mock_fetch.call_count

    assert asyncio.run(_run()) >= 2


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
            screen = PlannerScreen(config={})
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 3
    titles = [t["title"] for t in items]
    assert "Define Q3 OKRs" in titles


def test_fetch_items_fixture_search_filter() -> None:
    """fetch_items filters by search term when fixtures are loaded."""
    import os
    import pathlib

    fixture_dir = str(pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures")

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": fixture_dir}):
            screen = PlannerScreen(config={})
            return await screen.fetch_items(search="architecture")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["title"] == "Review architecture proposal"


def test_fetch_items_fixture_search_no_match() -> None:
    """fetch_items returns [] when search matches nothing."""
    import os
    import pathlib

    fixture_dir = str(pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures")

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": fixture_dir}):
            screen = PlannerScreen(config={})
            return await screen.fetch_items(search="xyzzy-no-match")

    items = asyncio.run(_run())
    assert items == []


def test_fetch_items_api_returns_none() -> None:
    """fetch_items returns [] when api_get returns None (no fixtures)."""

    async def _run() -> list[dict]:
        screen = PlannerScreen(config={})
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_planner.api.api_get", return_value=None),
        ):
            return await screen.fetch_items()

    assert asyncio.run(_run()) == []


def test_fetch_items_api_returns_data() -> None:
    """fetch_items normalizes data from api_get."""
    raw = {
        "value": [
            {
                "id": "plan-task-001",
                "planId": "plan-aaa",
                "bucketId": "bucket-x1",
                "title": "My planner task",
                "percentComplete": 0,
                "priority": 1,
                "dueDateTime": "2026-06-25T00:00:00Z",
                "startDateTime": None,
                "completedDateTime": None,
                "createdDateTime": "2026-06-01T09:00:00Z",
                "assignments": {},
                "checklistItemCount": 0,
                "activeChecklistItemCount": 0,
                "referenceCount": 0,
                "hasDescription": False,
            }
        ]
    }

    async def _run() -> list[dict]:
        screen = PlannerScreen(config={})
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_planner.api.api_get", return_value=raw),
        ):
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["title"] == "My planner task"
    assert items[0]["status"] == "NotStarted"
    assert items[0]["priorityLabel"] == "urgent"


# ---------------------------------------------------------------------------
# menu_config
# ---------------------------------------------------------------------------


def test_menu_config_returns_tuple() -> None:
    sc = PlannerScreen()
    title, fields = sc.menu_config()
    assert isinstance(title, str)
    assert "Planner" in title
    assert isinstance(fields, list)


# ---------------------------------------------------------------------------
# render_row / render_detail via screen methods
# ---------------------------------------------------------------------------


def test_render_row_via_screen() -> None:
    sc = PlannerScreen()
    task = _tasks(1)[0]
    row = sc.render_row(task, 80)
    assert isinstance(row, str)
    assert len(row) > 0


def test_render_detail_via_screen() -> None:
    sc = PlannerScreen()
    task = _tasks(1)[0]
    detail = sc.render_detail(task)
    assert isinstance(detail, str)
    assert "Planner Task" in detail


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def test_planner_registered_in_registry() -> None:
    from owa_tui.screens import SCREEN_REGISTRY

    assert "planner" in SCREEN_REGISTRY
    assert SCREEN_REGISTRY["planner"]["label"] == "Planner"
    assert SCREEN_REGISTRY["planner"]["screen_class"] is PlannerScreen


# ---------------------------------------------------------------------------
# Worker: fetch populates list via pilot
# ---------------------------------------------------------------------------


def test_fetch_worker_populates_via_pilot() -> None:
    """Ensure the fetch worker path (no initial_items) works with mocked fetch."""
    items = _tasks(2)

    async def _run() -> int:
        with patch.object(PlannerScreen, "fetch_items", return_value=items):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return len(app.screen._items)

    assert asyncio.run(_run()) == 2


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        with patch.object(PlannerScreen, "fetch_items", side_effect=RuntimeError("boom")):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return app.screen._status

    assert "error: boom" in asyncio.run(_run())


# ---------------------------------------------------------------------------
# help_text
# ---------------------------------------------------------------------------


def test_help_text_contains_keys() -> None:
    sc = PlannerScreen()
    ht = sc.help_text()
    assert "j" in ht or "move" in ht
    # Read-only: no complete-toggle mention
    assert "complete" not in ht.lower()


def test_help_text_no_complete_toggle() -> None:
    """PlannerScreen v1 is read-only — no complete-toggle in help text."""
    sc = PlannerScreen()
    ht = sc.help_text()
    assert "complete" not in ht.lower()
