"""Unit and Pilot tests for AdoScreen.

Coverage targets:
- _row_text / _detail_text pure helpers (no Textual)
- AdoScreen.fetch_items with fixture + search filter paths
- AdoScreen pilot: list renders, j+l opens detail, h closes,
  menu, refresh, empty result, search, error status.
- Live two-step fetch path with ado_request mocked.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.ado import AdoScreen, _detail_text, _row_text

# ---------------------------------------------------------------------------
# Sample work-item dicts (already normalized — same shape normalize_work_item
# returns)
# ---------------------------------------------------------------------------


def _items(n: int = 3) -> list[dict]:
    states = ["Active", "New", "Resolved"]
    types = ["Task", "User Story", "Bug"]
    return [
        {
            "id": 1000 + i,
            "title": f"ADO Work Item {i}",
            "state": states[i % len(states)],
            "type": types[i % len(types)],
            "priority": (i % 4) + 1,
            "assignedTo": "Test User",
            "iteration": f"myproject\\Sprint {40 + i}",
            "area": "myproject\\Platform",
            "tags": f"tag{i}",
            "changed": f"2026-06-{18 + i:02d}T10:00:00Z",
            "url": f"https://dev.azure.com/contoso/myproject/_apis/wit/workItems/{1000 + i}",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Helpers: app factory
# ---------------------------------------------------------------------------


def _make_app(**screen_kw: Any) -> App:
    """Return a Textual App that pushes an AdoScreen on mount."""

    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(AdoScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Pure helper tests — no Textual app needed
# ---------------------------------------------------------------------------


def test_row_text_active_shows_tilde() -> None:
    item = {"title": "Active item", "state": "Active", "type": "Task", "priority": 2}
    row = _row_text(item, width=80)
    assert "[~]" in row
    assert "Active item" in row


def test_row_text_new_shows_empty_box() -> None:
    item = {"title": "New item", "state": "New", "type": "Task", "priority": 3}
    row = _row_text(item, width=80)
    assert "[ ]" in row


def test_row_text_resolved_shows_dot() -> None:
    item = {"title": "Resolved item", "state": "Resolved", "type": "Bug", "priority": 3}
    row = _row_text(item, width=80)
    assert "[.]" in row


def test_row_text_closed_shows_x() -> None:
    item = {"title": "Closed item", "state": "Closed", "type": "Task", "priority": 4}
    row = _row_text(item, width=80)
    assert "[x]" in row


def test_row_text_priority_1_shows_bang_bang() -> None:
    item = {"title": "Critical", "state": "Active", "type": "Bug", "priority": 1}
    row = _row_text(item, width=80)
    assert "!!" in row


def test_row_text_priority_2_shows_bang_space() -> None:
    item = {"title": "High", "state": "Active", "type": "Task", "priority": 2}
    row = _row_text(item, width=80)
    assert "! " in row


def test_row_text_shows_id_and_type() -> None:
    item = {"id": 9999, "title": "With ID", "state": "New", "type": "User Story", "priority": 3}
    row = _row_text(item, width=120)
    assert "#9999" in row
    assert "User Story" in row


def test_row_text_truncates_long_title() -> None:
    item = {"title": "X" * 200, "state": "New", "type": "Task", "priority": 3}
    row = _row_text(item, width=50)
    assert len(row) <= 65  # tolerance for prefix


def test_row_text_empty_title() -> None:
    row = _row_text({}, width=80)
    assert "(no title)" in row


def test_detail_text_full() -> None:
    item = {
        "id": 1234,
        "title": "Full work item",
        "type": "Bug",
        "state": "Active",
        "priority": 1,
        "assignedTo": "Alice",
        "iteration": "myproject\\Sprint 42",
        "area": "myproject\\Backend",
        "tags": "api; regression",
        "changed": "2026-06-18T10:00:00Z",
        "url": "https://dev.azure.com/contoso/myproject/_apis/wit/workItems/1234",
    }
    detail = _detail_text(item)
    assert "Full work item" in detail
    assert "#1234" in detail
    assert "Bug" in detail
    assert "Active" in detail
    assert "Alice" in detail
    assert "Sprint 42" in detail
    assert "api; regression" in detail
    assert "2026-06-18" in detail
    assert "dev.azure.com" in detail


def test_detail_text_minimal() -> None:
    detail = _detail_text({"title": "Simple item"})
    assert "Simple item" in detail


def test_detail_text_empty_item() -> None:
    detail = _detail_text({})
    assert "(no title)" in detail


def test_detail_text_changed_truncated_to_date() -> None:
    item = {"title": "T", "changed": "2026-06-18T10:00:00Z"}
    detail = _detail_text(item)
    assert "2026-06-18" in detail
    # Should not include the time portion
    assert "T10:00:00Z" not in detail


def test_detail_text_no_url_no_url_line() -> None:
    item = {"title": "No URL item", "state": "New"}
    detail = _detail_text(item)
    assert "URL:" not in detail


# ---------------------------------------------------------------------------
# Pilot tests — AdoScreen with preloaded items
# ---------------------------------------------------------------------------


def test_list_renders_items() -> None:
    async def _run() -> bool:
        app = _make_app(initial_items=_items(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            items = app.screen._items
            return len(items) == 3

    assert asyncio.run(_run())


def test_j_moves_cursor_down() -> None:
    async def _run() -> int:
        app = _make_app(initial_items=_items(3), detail_pane_mode="right")
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
        app = _make_app(initial_items=_items(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("l")
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "detail"


def test_h_closes_detail() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items(3), detail_pane_mode="right")
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
        app = _make_app(initial_items=_items(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) >= 1


def test_detail_pane_off_not_mounted() -> None:
    from owa_tui.screens.base.screen import _DetailPane

    async def _run() -> int:
        app = _make_app(initial_items=_items(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) == 0


def test_escape_opens_menu() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "SettingsOverlay"


def test_q_quits() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) != "AdoScreen"


def test_search_key_opens_modal() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("/")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "_SearchModal"


def test_refresh_refetches() -> None:
    """r key triggers a re-fetch."""
    items = _items(2)

    async def _run() -> int:
        with patch.object(AdoScreen, "fetch_items", return_value=items) as mock_fetch:
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
            screen = AdoScreen(config={})
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 3
    titles = [i["title"] for i in items]
    assert "Migrate auth flow to MSAL v3" in titles


def test_fetch_items_fixture_search_filter() -> None:
    """fetch_items filters by search term when fixtures are loaded."""
    import os
    import pathlib

    fixture_dir = str(pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures")

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": fixture_dir}):
            screen = AdoScreen(config={})
            return await screen.fetch_items(search="keybinding")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["title"] == "Document owa-tui ADO screen keybindings"


def test_fetch_items_fixture_search_no_match() -> None:
    """fetch_items returns [] when search matches nothing."""
    import os
    import pathlib

    fixture_dir = str(pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures")

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": fixture_dir}):
            screen = AdoScreen(config={})
            return await screen.fetch_items(search="xyzzy-no-match")

    items = asyncio.run(_run())
    assert items == []


def test_fetch_items_no_org_returns_empty() -> None:
    """fetch_items returns [] when org/project are missing from config."""

    async def _run() -> list[dict]:
        screen = AdoScreen(config={})
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_ado.config.load_config", return_value={}),
        ):
            return await screen.fetch_items()

    assert asyncio.run(_run()) == []


def test_fetch_items_wiql_returns_none() -> None:
    """fetch_items returns [] when WIQL POST returns None."""

    async def _run() -> list[dict]:
        screen = AdoScreen(config={"ado_org": "contoso", "ado_project": "myproject"})
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_ado.config.load_config", return_value={}),
            patch("owa_ado.auth.org_base", return_value="https://dev.azure.com/contoso"),
            patch("owa_ado.api.ado_request", return_value=None),
        ):
            return await screen.fetch_items()

    assert asyncio.run(_run()) == []


def test_fetch_items_wiql_empty_list() -> None:
    """fetch_items returns [] when WIQL returns no work items."""

    async def _run() -> list[dict]:
        screen = AdoScreen(config={"ado_org": "contoso", "ado_project": "myproject"})
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_ado.config.load_config", return_value={}),
            patch("owa_ado.auth.org_base", return_value="https://dev.azure.com/contoso"),
            patch("owa_ado.api.ado_request", return_value={"workItems": []}),
        ):
            return await screen.fetch_items()

    assert asyncio.run(_run()) == []


def test_fetch_items_live_two_step_path() -> None:
    """fetch_items normalizes data from the two-step live fetch."""
    wiql_response = {"workItems": [{"id": 101}, {"id": 102}]}
    batch_response = {
        "value": [
            {
                "id": 101,
                "url": "https://dev.azure.com/contoso/_apis/wit/workItems/101",
                "fields": {
                    "System.Id": 101,
                    "System.WorkItemType": "Task",
                    "System.Title": "First live item",
                    "System.State": "Active",
                    "System.AssignedTo": {"displayName": "Alice"},
                    "System.IterationPath": "myproject\\Sprint 1",
                    "System.AreaPath": "myproject\\Backend",
                    "System.Tags": "",
                    "System.ChangedDate": "2026-06-18T00:00:00Z",
                },
            },
            {
                "id": 102,
                "url": "https://dev.azure.com/contoso/_apis/wit/workItems/102",
                "fields": {
                    "System.Id": 102,
                    "System.WorkItemType": "Bug",
                    "System.Title": "Second live item",
                    "System.State": "New",
                    "System.AssignedTo": {"displayName": "Bob"},
                    "System.IterationPath": "myproject\\Sprint 1",
                    "System.AreaPath": "myproject\\Frontend",
                    "System.Tags": "ui",
                    "System.ChangedDate": "2026-06-17T00:00:00Z",
                },
            },
        ]
    }

    # The first call (POST) returns WIQL ids; the second (GET) returns batch.
    call_count = {"n": 0}

    def _mock_ado_request(method, base, endpoint, token, **kwargs):
        call_count["n"] += 1
        if method == "POST":
            return wiql_response
        return batch_response

    async def _run() -> list[dict]:
        screen = AdoScreen(config={"ado_org": "contoso", "ado_project": "myproject"})
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_ado.config.load_config", return_value={}),
            patch("owa_ado.auth.org_base", return_value="https://dev.azure.com/contoso"),
            patch("owa_ado.api.ado_request", side_effect=_mock_ado_request),
        ):
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 2
    assert items[0]["title"] == "First live item"
    assert items[0]["state"] == "Active"
    assert items[0]["assignedTo"] == "Alice"
    assert items[1]["title"] == "Second live item"
    assert items[1]["type"] == "Bug"
    # Verify both steps were called
    assert call_count["n"] == 2


def test_fetch_items_live_batch_returns_none() -> None:
    """fetch_items returns [] when batch GET returns None."""

    def _mock_ado_request(method, base, endpoint, token, **kwargs):
        if method == "POST":
            return {"workItems": [{"id": 1}]}
        return None  # batch GET fails

    async def _run() -> list[dict]:
        screen = AdoScreen(config={"ado_org": "contoso", "ado_project": "myproject"})
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_ado.config.load_config", return_value={}),
            patch("owa_ado.auth.org_base", return_value="https://dev.azure.com/contoso"),
            patch("owa_ado.api.ado_request", side_effect=_mock_ado_request),
        ):
            return await screen.fetch_items()

    assert asyncio.run(_run()) == []


# ---------------------------------------------------------------------------
# menu_config
# ---------------------------------------------------------------------------


def test_menu_config_returns_tuple() -> None:
    sc = AdoScreen()
    title, fields = sc.menu_config()
    assert isinstance(title, str)
    assert "Azure DevOps" in title
    assert isinstance(fields, list)
    assert fields == []


# ---------------------------------------------------------------------------
# render_row / render_detail via screen methods
# ---------------------------------------------------------------------------


def test_render_row_via_screen() -> None:
    sc = AdoScreen()
    item = _items(1)[0]
    row = sc.render_row(item, 80)
    assert isinstance(row, str)
    assert len(row) > 0


def test_render_detail_via_screen() -> None:
    sc = AdoScreen()
    item = _items(1)[0]
    detail = sc.render_detail(item)
    assert isinstance(detail, str)
    assert "ADO Work Item" in detail


# ---------------------------------------------------------------------------
# help_text
# ---------------------------------------------------------------------------


def test_help_text_contains_keys() -> None:
    sc = AdoScreen()
    ht = sc.help_text()
    assert "j" in ht or "move" in ht


def test_help_text_no_mutation_actions() -> None:
    """AdoScreen v1 is read-only."""
    sc = AdoScreen()
    ht = sc.help_text()
    assert "create" not in ht.lower()
    assert "edit" not in ht.lower()


# ---------------------------------------------------------------------------
# open_browser_for
# ---------------------------------------------------------------------------


def test_open_browser_for_returns_url() -> None:
    sc = AdoScreen()
    item = {"url": "https://dev.azure.com/contoso/proj/_apis/wit/workItems/42"}
    assert sc.open_browser_for(item) == item["url"]


def test_open_browser_for_no_url_returns_none() -> None:
    sc = AdoScreen()
    assert sc.open_browser_for({}) is None


# ---------------------------------------------------------------------------
# Worker: fetch populates list via pilot
# ---------------------------------------------------------------------------


def test_fetch_worker_populates_via_pilot() -> None:
    """Ensure the fetch worker path (no initial_items) works with mocked fetch."""
    items = _items(2)

    async def _run() -> int:
        with patch.object(AdoScreen, "fetch_items", return_value=items):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return len(app.screen._items)

    assert asyncio.run(_run()) == 2


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        with patch.object(AdoScreen, "fetch_items", side_effect=RuntimeError("boom")):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return app.screen._status

    assert "error: boom" in asyncio.run(_run())


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_ado_registered_in_registry() -> None:
    from owa_tui.screens import SCREEN_REGISTRY

    assert "ado" in SCREEN_REGISTRY
    assert SCREEN_REGISTRY["ado"]["label"] == "Azure DevOps"
    assert SCREEN_REGISTRY["ado"]["screen_class"] is AdoScreen
