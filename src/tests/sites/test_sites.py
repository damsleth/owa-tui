"""Unit and Pilot tests for SitesScreen.

Coverage targets:
- _row_text / _detail_text / _slug pure helpers (no Textual)
- SitesScreen.load_node with fixture + search filter paths
- SitesScreen pilot: list renders, j+l drills into a list, h goes back,
  item detail, menu, refresh, search, error status.
- Mocked live two-step: paginate_sp returns lists then items.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.sites import (
    SitesScreen,
    TreeNode,
    _detail_text,
    _row_text,
    _slug,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FIXTURE_DIR = str(
    pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures"
)


def _list_item(
    title: str = "Project Tracker",
    item_count: int = 42,
    base_template: int = 100,
    list_id: str = "list-001",
) -> dict:
    return {
        "title": title,
        "id": list_id,
        "itemCount": item_count,
        "baseTemplate": base_template,
        "hidden": False,
        "_kind": "list",
    }


def _sp_item(
    item_id: int = 101,
    title: str = "Crayon Norway — Q3 delivery roadmap",
    file_leaf_ref: str = "Q3Roadmap.docx",
    modified: str = "2026-06-18T14:22:00Z",
) -> dict:
    return {
        "Id": item_id,
        "Title": title,
        "FileLeafRef": file_leaf_ref,
        "Modified": modified,
        "Created": "2026-04-01T08:00:00Z",
        "AuthorId": 7,
        "_kind": "item",
    }


def _items(include_list: bool = True, include_item: bool = True) -> list[dict]:
    result = []
    if include_list:
        result.append(_list_item())
    if include_item:
        result.append(_sp_item())
    return result


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app(**screen_kw: Any) -> App:
    """Return a Textual App that pushes a SitesScreen on mount."""

    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(SitesScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Pure helper tests — no Textual app needed
# ---------------------------------------------------------------------------


def test_slug_root() -> None:
    assert _slug("") == "root"


def test_slug_simple() -> None:
    assert _slug("Documents") == "Documents"


def test_slug_spaces() -> None:
    assert _slug("Project Tracker") == "Project_Tracker"


def test_slug_nested() -> None:
    assert _slug("Q2 Reports/Slides") == "Q2_Reports_Slides"


def test_row_text_list_shows_icon_and_count() -> None:
    item = _list_item(title="Project Tracker", item_count=42)
    row = _row_text(item, width=80)
    assert "\U0001f4cb" in row  # clipboard icon
    assert "Project Tracker" in row
    assert "42 items" in row


def test_row_text_list_no_item_count() -> None:
    item = _list_item(item_count=None)  # type: ignore[arg-type]
    item["itemCount"] = None
    row = _row_text(item, width=80)
    assert "—" in row


def test_row_text_item_shows_icon_and_title() -> None:
    item = _sp_item(title="Crayon Norway — Q3 delivery roadmap")
    row = _row_text(item, width=80)
    assert "\U0001f4c4" in row  # document icon
    assert "Crayon Norway" in row


def test_row_text_truncates_long_title() -> None:
    item = _sp_item(title="A" * 200)
    row = _row_text(item, width=50)
    assert "…" in row


def test_row_text_item_no_title_falls_back_to_file_leaf_ref() -> None:
    item = _sp_item(title="")
    item["Title"] = ""
    row = _row_text(item, width=80)
    # Falls back to FileLeafRef
    assert "Q3Roadmap.docx" in row


def test_detail_text_list() -> None:
    item = _list_item(title="Project Tracker", item_count=42)
    detail = _detail_text(item)
    assert "Project Tracker" in detail
    assert "list" in detail
    assert "42" in detail


def test_detail_text_item() -> None:
    item = _sp_item(title="Crayon Norway — Q3 delivery roadmap")
    detail = _detail_text(item)
    assert "Crayon Norway" in detail
    assert "item" in detail


def test_detail_text_empty_dict() -> None:
    detail = _detail_text({})
    assert "(unnamed)" in detail


def test_detail_text_item_with_modified() -> None:
    item = _sp_item(modified="2026-06-18T14:22:00Z")
    detail = _detail_text(item)
    assert "2026-06-18" in detail


# ---------------------------------------------------------------------------
# Pilot tests — SitesScreen with preloaded items
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


def test_j_then_l_drills_into_list() -> None:
    """j selects the list at idx 0, l drills in — pushes a new node."""
    list_row = _list_item()
    child_items = [_sp_item()]

    async def _run() -> tuple[int, int]:
        app = _make_app(initial_items=[list_row], detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.pause(0.05)
            with patch.object(SitesScreen, "load_node", return_value=child_items):
                await pilot.press("l")
                await pilot.pause(0.3)
                stack_depth = len(app.screen._node_stack)
                item_count = len(app.screen._items)
            return stack_depth, item_count

    stack_depth, item_count = asyncio.run(_run())
    assert stack_depth == 2  # root + drilled node
    assert item_count == 1


def test_l_on_item_opens_detail_mode() -> None:
    """j twice (list at 0, item at 1), l opens detail for the item."""

    async def _run() -> str:
        app = _make_app(initial_items=_items(), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("l")
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "detail"


def test_h_closes_detail_on_item() -> None:
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

    assert asyncio.run(_run()) != "SitesScreen"


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
        with patch.object(SitesScreen, "fetch_items", return_value=items) as mock_fetch:
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
    """load_node returns root lists from sites.json when OWA_TUI_FIXTURES is set."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = SitesScreen(config={})
            root_node = TreeNode(id="", label="SharePoint Sites")
            return await screen.load_node(root_node, "")

    items = asyncio.run(_run())
    assert len(items) >= 1
    titles = [i["title"] for i in items]
    assert "Project Tracker" in titles


def test_load_node_fixture_mode_drilled_list() -> None:
    """load_node loads drilled-list fixture by slug when present."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = SitesScreen(config={})
            node = TreeNode(id="Project Tracker", label="Project Tracker")
            return await screen.load_node(node, "")

    items = asyncio.run(_run())
    assert len(items) >= 1
    titles = [i.get("Title") for i in items]
    assert "Crayon Norway — Q3 delivery roadmap" in titles


def test_load_node_fixture_search_filter() -> None:
    """load_node filters by search term within fixture data."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = SitesScreen(config={})
            root_node = TreeNode(id="", label="SharePoint Sites")
            return await screen.load_node(root_node, "risk")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert "Risk" in items[0]["title"]


def test_load_node_fixture_search_no_match() -> None:
    """load_node returns [] when search matches nothing."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = SitesScreen(config={})
            root_node = TreeNode(id="", label="SharePoint Sites")
            return await screen.load_node(root_node, "xyzzy-no-match-123")

    assert asyncio.run(_run()) == []


def test_load_node_missing_fixture_falls_back_to_root() -> None:
    """load_node falls back to sites.json when a drilled fixture is missing."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": _FIXTURE_DIR}):
            screen = SitesScreen(config={})
            node = TreeNode(id="NonExistentList", label="NonExistentList")
            return await screen.load_node(node, "")

    items = asyncio.run(_run())
    # Falls back to root sites.json — returns lists
    assert len(items) >= 1
    titles = [i.get("title") for i in items]
    assert "Project Tracker" in titles


def test_load_node_returns_empty_when_raw_is_none() -> None:
    """load_node returns [] when both fixture and live call return None."""

    async def _run() -> list[dict]:
        screen = SitesScreen(config={})
        root_node = TreeNode(id="", label="SharePoint Sites")
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_sites.auth.setup_auth", return_value=("tok", "https://example.sharepoint.com")),
            patch("owa_sites.config.load_config", return_value={}),
            patch("owa_sites.api.paginate_sp", return_value=None),
        ):
            return await screen.load_node(root_node, "")

    assert asyncio.run(_run()) == []


def test_load_node_live_root_lists() -> None:
    """load_node normalizes live paginate_sp data for root (lists)."""
    raw_sp_lists = [
        {"Title": "Live List", "Id": "live-001", "ItemCount": 5, "BaseTemplate": 100, "Hidden": False}
    ]

    async def _run() -> list[dict]:
        screen = SitesScreen(config={})
        root_node = TreeNode(id="", label="SharePoint Sites")
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_sites.auth.setup_auth", return_value=("tok", "https://contoso.sharepoint.com")),
            patch("owa_sites.config.load_config", return_value={}),
            patch("owa_sites.api.paginate_sp", return_value=raw_sp_lists),
        ):
            return await screen.load_node(root_node, "")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["title"] == "Live List"
    assert items[0]["_kind"] == "list"
    assert items[0]["itemCount"] == 5


def test_load_node_live_drilled_items() -> None:
    """load_node normalizes live paginate_sp data for a drilled list (items)."""
    raw_sp_items = [
        {
            "Id": 1,
            "Title": "Live Item",
            "FileLeafRef": "LiveItem.docx",
            "Modified": "2026-06-01T00:00:00Z",
            "Created": "2026-01-01T00:00:00Z",
            "AuthorId": 2,
        }
    ]

    async def _run() -> list[dict]:
        screen = SitesScreen(config={})
        node = TreeNode(id="Project Tracker", label="Project Tracker")
        with (
            patch("owa_tui.fixtures.enabled", return_value=False),
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_sites.auth.setup_auth", return_value=("tok", "https://contoso.sharepoint.com")),
            patch("owa_sites.config.load_config", return_value={}),
            patch("owa_sites.api.paginate_sp", return_value=raw_sp_items),
        ):
            return await screen.load_node(node, "")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["Title"] == "Live Item"
    assert items[0]["_kind"] == "item"


# ---------------------------------------------------------------------------
# is_container / child_node / render hooks
# ---------------------------------------------------------------------------


def test_is_container_list() -> None:
    sc = SitesScreen()
    assert sc.is_container(_list_item()) is True


def test_is_container_item() -> None:
    sc = SitesScreen()
    assert sc.is_container(_sp_item()) is False


def test_is_container_unknown() -> None:
    sc = SitesScreen()
    assert sc.is_container({"_kind": "unknown"}) is False


def test_child_node_from_list() -> None:
    sc = SitesScreen()
    node = sc.child_node(_list_item(title="Project Tracker"))
    assert node.id == "Project Tracker"
    assert node.label == "Project Tracker"


def test_child_node_empty_title() -> None:
    sc = SitesScreen()
    node = sc.child_node({"title": "", "_kind": "list"})
    assert node.id == ""


def test_render_row_via_screen_list() -> None:
    sc = SitesScreen()
    row = sc.render_row(_list_item(), 80)
    assert isinstance(row, str)
    assert "Project Tracker" in row


def test_render_row_via_screen_item() -> None:
    sc = SitesScreen()
    row = sc.render_row(_sp_item(), 80)
    assert isinstance(row, str)
    assert "Crayon Norway" in row


def test_render_detail_via_screen_list() -> None:
    sc = SitesScreen()
    detail = sc.render_detail(_list_item())
    assert "Project Tracker" in detail


def test_render_detail_via_screen_item() -> None:
    sc = SitesScreen()
    detail = sc.render_detail(_sp_item())
    assert "Crayon Norway" in detail


def test_menu_config_returns_tuple() -> None:
    sc = SitesScreen()
    title, fields = sc.menu_config()
    assert isinstance(title, str)
    assert "SharePoint" in title
    assert isinstance(fields, list)


def test_help_text_contains_keys() -> None:
    sc = SitesScreen()
    ht = sc.help_text()
    assert "j" in ht
    assert "l" in ht
    assert "h" in ht


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_sites_registered_in_registry() -> None:
    from owa_tui.screens import SCREEN_REGISTRY

    assert "sites" in SCREEN_REGISTRY
    assert SCREEN_REGISTRY["sites"]["label"] == "SharePoint"
    assert SCREEN_REGISTRY["sites"]["screen_class"] is SitesScreen


# ---------------------------------------------------------------------------
# Worker: fetch populates list via pilot
# ---------------------------------------------------------------------------


def test_fetch_worker_populates_via_pilot() -> None:
    """Ensure the fetch worker path (no initial_items) works with mocked load_node."""
    items = _items()

    async def _run() -> int:
        with patch.object(SitesScreen, "fetch_items", return_value=items):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return len(app.screen._items)

    assert asyncio.run(_run()) == 2


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        with patch.object(SitesScreen, "fetch_items", side_effect=RuntimeError("sp down")):
            app = _make_app(detail_pane_mode="off")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return app.screen._status

    assert "error: sp down" in asyncio.run(_run())


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
