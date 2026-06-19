"""Unit and Pilot tests for DriveScreen.

Coverage targets:
- _row_text / _detail_text / _fmt_size / _slug pure helpers (no Textual)
- DriveScreen.load_node with fixture + search filter paths
- DriveScreen pilot: list renders, j+l drills folder, h goes back,
  file detail, menu, refresh, search, error status.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.drive import (
    DriveScreen,
    TreeNode,
    _detail_text,
    _fmt_size,
    _row_text,
    _slug,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_DIR = str(
    pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures"
)


def _folder_item(
    name: str = "Q2 Reports",
    child_count: int = 3,
    parent_path: str = "/",
) -> dict:
    return {
        "id": f"folder-{name}",
        "name": name,
        "kind": "folder",
        "size": None,
        "lastModified": "2026-04-01T08:00:00Z",
        "webUrl": f"https://example.com/{name}",
        "parentPath": parent_path,
        "mimeType": "",
        "childCount": child_count,
    }


def _file_item(
    name: str = "Architecture Decision Record.docx",
    size: int = 184320,
    parent_path: str = "/",
) -> dict:
    return {
        "id": f"file-{name}",
        "name": name,
        "kind": "file",
        "size": size,
        "lastModified": "2026-05-15T09:30:00Z",
        "webUrl": f"https://example.com/{name}",
        "parentPath": parent_path,
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "childCount": None,
    }


def _items(include_folder: bool = True, include_file: bool = True) -> list[dict]:
    result = []
    if include_folder:
        result.append(_folder_item())
    if include_file:
        result.append(_file_item())
    return result


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app(**screen_kw: Any) -> App:
    """Return a Textual App that pushes a DriveScreen on mount."""

    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(DriveScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Pure helper tests — no Textual app needed
# ---------------------------------------------------------------------------


def test_fmt_size_none() -> None:
    assert _fmt_size(None) == "—"


def test_fmt_size_bytes() -> None:
    assert _fmt_size(500) == "500 B"


def test_fmt_size_kilobytes() -> None:
    result = _fmt_size(2048)
    assert "KB" in result


def test_fmt_size_megabytes() -> None:
    result = _fmt_size(2 * 1024 * 1024)
    assert "MB" in result


def test_fmt_size_gigabytes() -> None:
    result = _fmt_size(2 * 1024**3)
    assert "GB" in result


def test_slug_root() -> None:
    assert _slug("") == "root"


def test_slug_simple() -> None:
    assert _slug("Documents") == "Documents"


def test_slug_spaces() -> None:
    assert _slug("Q2 Reports") == "Q2_Reports"


def test_slug_nested() -> None:
    assert _slug("Q2 Reports/Slides") == "Q2_Reports_Slides"


def test_row_text_folder_shows_icon_and_child_count() -> None:
    item = _folder_item(child_count=3)
    row = _row_text(item, width=80)
    assert "\U0001f4c1" in row  # folder icon
    assert "Q2 Reports" in row
    assert "3 items" in row


def test_row_text_folder_no_child_count() -> None:
    item = _folder_item(child_count=None)  # type: ignore[arg-type]
    item["childCount"] = None
    row = _row_text(item, width=80)
    assert "—" in row


def test_row_text_file_shows_icon_and_size() -> None:
    item = _file_item(size=184320)
    row = _row_text(item, width=80)
    assert "\U0001f4c4" in row  # file icon
    assert "Architecture Decision Record" in row
    assert "KB" in row


def test_row_text_truncates_long_name() -> None:
    item = _file_item(name="A" * 200)
    row = _row_text(item, width=50)
    assert "…" in row


def test_row_text_empty_name() -> None:
    item = _file_item(name="")
    row = _row_text(item, width=80)
    assert "(unnamed)" in row


def test_detail_text_folder() -> None:
    item = _folder_item(child_count=5)
    detail = _detail_text(item)
    assert "Q2 Reports" in detail
    assert "folder" in detail
    assert "5" in detail


def test_detail_text_file() -> None:
    item = _file_item()
    detail = _detail_text(item)
    assert "Architecture Decision Record" in detail
    assert "file" in detail
    assert "KB" in detail
    assert "wordprocessingml" in detail


def test_detail_text_empty() -> None:
    detail = _detail_text({})
    assert "(unnamed)" in detail


def test_detail_text_with_modified() -> None:
    item = _file_item()
    detail = _detail_text(item)
    assert "2026-05-15" in detail


def test_detail_text_with_url() -> None:
    item = _file_item()
    detail = _detail_text(item)
    assert "https://example.com" in detail


# ---------------------------------------------------------------------------
# Pilot tests — DriveScreen with preloaded items
# ---------------------------------------------------------------------------


def test_list_renders_items() -> None:
    async def _run() -> bool:
        app = _make_app(initial_items=_items(), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            items = app.screen._items
            return len(items) == 2

    assert asyncio.run(_run())


def test_j_moves_cursor_down() -> None:
    async def _run() -> int:
        app = _make_app(initial_items=_items(), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.pause(0.05)
            return app.screen._selected_idx

    assert asyncio.run(_run()) == 1


def test_j_then_l_drills_into_folder() -> None:
    """j selects the folder (single item at idx 0), l drills in — pushes a new node.

    We start with only the folder in initial_items so index 0 is always the
    folder regardless of any initial selection state.  j is pressed first (as
    required by tui-test gotcha) which stays at idx 0, then l drills in.
    """
    folder = _folder_item()
    child_items = [_file_item(name="Child File.docx")]

    async def _run() -> tuple[int, int]:
        # Single-item list — the folder is always at index 0.
        app = _make_app(initial_items=[folder], detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            # j selects the folder (wraps at single item, stays at 0).
            await pilot.press("j")
            await pilot.pause(0.05)
            # Patch load_node to return child items for the drilled folder.
            with patch.object(DriveScreen, "load_node", return_value=child_items):
                await pilot.press("l")
                await pilot.pause(0.3)
                stack_depth = len(app.screen._node_stack)
                item_count = len(app.screen._items)
            return stack_depth, item_count

    stack_depth, item_count = asyncio.run(_run())
    assert stack_depth == 2  # root + drilled node
    assert item_count == 1   # child items loaded


def test_l_on_file_opens_detail_mode() -> None:
    """j to file (idx 1), l to open detail."""
    async def _run() -> str:
        # File is at index 1 — press j twice from index 0 to reach it.
        app = _make_app(initial_items=_items(), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("l")
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "detail"


def test_h_closes_detail_on_file() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items(), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("l")
            await pilot.press("h")
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "list"


def test_escape_opens_menu() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items(), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "SettingsOverlay"


def test_q_quits() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items(), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) != "DriveScreen"


def test_search_key_opens_modal() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_items())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("/")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "_SearchModal"


def test_refresh_refetches() -> None:
    """r key triggers a re-fetch."""
    items = _items()

    async def _run() -> int:
        with patch.object(DriveScreen, "fetch_items", return_value=items) as mock_fetch:
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("r")
                await pilot.pause(0.3)
                return mock_fetch.call_count

    assert asyncio.run(_run()) >= 2


# ---------------------------------------------------------------------------
# load_node tests (async, no Textual app)
# ---------------------------------------------------------------------------


def test_load_node_fixture_mode_root() -> None:
    """load_node returns root fixture data when OWA_TUI_FIXTURES is set."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = DriveScreen(config={})
            root_node = TreeNode(id="", label="OneDrive")
            return await screen.load_node(root_node, "")

    items = asyncio.run(_run())
    assert len(items) >= 1
    names = [i["name"] for i in items]
    assert "Q2 Reports" in names


def test_load_node_fixture_mode_subfolder() -> None:
    """load_node loads drilled-folder fixture by slug when present."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = DriveScreen(config={})
            node = TreeNode(id="Q2 Reports", label="Q2 Reports")
            return await screen.load_node(node, "")

    items = asyncio.run(_run())
    assert len(items) >= 1
    names = [i["name"] for i in items]
    assert "Q2 2026 Financial Summary.xlsx" in names


def test_load_node_fixture_search_filter() -> None:
    """load_node filters by search term within fixture data."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = DriveScreen(config={})
            root_node = TreeNode(id="", label="OneDrive")
            return await screen.load_node(root_node, "architecture")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert "Architecture" in items[0]["name"]


def test_load_node_fixture_search_no_match() -> None:
    """load_node returns [] when search matches nothing."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = DriveScreen(config={})
            root_node = TreeNode(id="", label="OneDrive")
            return await screen.load_node(root_node, "xyzzy-no-match-123")

    items = asyncio.run(_run())
    assert items == []


def test_load_node_api_returns_none() -> None:
    """load_node returns [] when api_request returns None (no fixtures)."""

    async def _run() -> list[dict]:
        screen = DriveScreen(config={})
        root_node = TreeNode(id="", label="OneDrive")
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_drive.api.api_request", return_value=None),
        ):
            return await screen.load_node(root_node, "")

    assert asyncio.run(_run()) == []


def test_load_node_api_returns_data() -> None:
    """load_node normalizes live Graph data."""
    raw = {
        "value": [
            {
                "id": "folder-live-001",
                "name": "Live Folder",
                "folder": {"childCount": 2},
                "parentReference": {
                    "driveId": "b!xyz",
                    "driveType": "business",
                    "id": "root",
                    "path": "/drive/root:",
                },
                "lastModifiedDateTime": "2026-06-01T00:00:00Z",
                "webUrl": "https://example.com/LiveFolder",
            }
        ]
    }

    async def _run() -> list[dict]:
        screen = DriveScreen(config={})
        root_node = TreeNode(id="", label="OneDrive")
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="tok"),
            patch("owa_drive.api.api_request", return_value=raw),
        ):
            return await screen.load_node(root_node, "")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["name"] == "Live Folder"
    assert items[0]["kind"] == "folder"
    assert items[0]["childCount"] == 2


def test_load_node_missing_fixture_falls_back_to_root() -> None:
    """load_node falls back to drive.json when a drilled fixture is missing."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = DriveScreen(config={})
            # "NonExistent" has no drive_NonExistent.json fixture — falls back
            node = TreeNode(id="NonExistent", label="NonExistent")
            return await screen.load_node(node, "")

    items = asyncio.run(_run())
    # Falls back to drive.json root listing
    assert len(items) >= 1
    names = [i["name"] for i in items]
    assert "Q2 Reports" in names


# ---------------------------------------------------------------------------
# is_container / child_node / render hooks
# ---------------------------------------------------------------------------


def test_is_container_folder() -> None:
    sc = DriveScreen()
    assert sc.is_container(_folder_item()) is True


def test_is_container_file() -> None:
    sc = DriveScreen()
    assert sc.is_container(_file_item()) is False


def test_is_container_unknown() -> None:
    sc = DriveScreen()
    assert sc.is_container({"kind": "unknown"}) is False


def test_child_node_root_parent() -> None:
    sc = DriveScreen()
    folder = _folder_item(name="Documents", parent_path="/")
    node = sc.child_node(folder)
    assert node.id == "Documents"
    assert node.label == "Documents"


def test_child_node_nested_parent() -> None:
    sc = DriveScreen()
    folder = _folder_item(name="Q1 Reports", parent_path="/Documents")
    node = sc.child_node(folder)
    assert node.id == "Documents/Q1 Reports"
    assert node.label == "Q1 Reports"


def test_render_row_via_screen() -> None:
    sc = DriveScreen()
    row = sc.render_row(_folder_item(), 80)
    assert isinstance(row, str)
    assert len(row) > 0
    assert "Q2 Reports" in row


def test_render_detail_via_screen() -> None:
    sc = DriveScreen()
    detail = sc.render_detail(_file_item())
    assert isinstance(detail, str)
    assert "Architecture Decision Record" in detail


def test_menu_config_returns_tuple() -> None:
    sc = DriveScreen()
    title, fields = sc.menu_config()
    assert isinstance(title, str)
    assert "OneDrive" in title
    assert isinstance(fields, list)


def test_help_text_contains_keys() -> None:
    sc = DriveScreen()
    ht = sc.help_text()
    assert "j" in ht
    assert "l" in ht
    assert "h" in ht


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_drive_registered_in_registry() -> None:
    from owa_tui.screens import SCREEN_REGISTRY

    assert "drive" in SCREEN_REGISTRY
    assert SCREEN_REGISTRY["drive"]["label"] == "OneDrive"
    assert SCREEN_REGISTRY["drive"]["screen_class"] is DriveScreen


# ---------------------------------------------------------------------------
# Worker: fetch populates list via pilot
# ---------------------------------------------------------------------------


def test_fetch_worker_populates_via_pilot() -> None:
    """Ensure the fetch worker path (no initial_items) works with mocked load_node."""
    items = _items()

    async def _run() -> int:
        with patch.object(DriveScreen, "fetch_items", return_value=items):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return len(app.screen._items)

    assert asyncio.run(_run()) == 2


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        with patch.object(DriveScreen, "fetch_items", side_effect=RuntimeError("api down")):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return app.screen._status

    assert "error: api down" in asyncio.run(_run())


# ---------------------------------------------------------------------------
# Detail pane mode
# ---------------------------------------------------------------------------


def test_detail_pane_right_mounted() -> None:
    from owa_tui.screens.base.screen import _DetailPane

    async def _run() -> int:
        app = _make_app(initial_items=_items(), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) >= 1


def test_detail_pane_off_not_mounted() -> None:
    from owa_tui.screens.base.screen import _DetailPane

    async def _run() -> int:
        app = _make_app(initial_items=_items(), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) == 0
