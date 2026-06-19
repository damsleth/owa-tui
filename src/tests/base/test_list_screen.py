"""Pilot tests for owa_tui.screens.base.OwaListScreen.

The base is proven with a concrete _FakeListScreen whose fetch_items returns
canned rows (or raises) — no live M365. Async helpers are wrapped in
asyncio.run() so plain pytest runs them (project convention, no pytest-asyncio).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, ListItem

from owa_tui.screens.base import OwaListScreen
from owa_tui.screens.base.screen import _DetailPane


def _rows(n: int = 3) -> list[dict]:
    return [{"id": f"r{i}", "name": f"Row {i}"} for i in range(n)]


class _FakeListScreen(OwaListScreen):
    """Concrete OwaListScreen for testing the base behaviour."""

    def __init__(self, *, fetch_rows: list[dict] | None = None, fetch_error: str = "", **kw: Any):
        super().__init__(tool_name="owa-fake", audience="graph", **kw)
        self._fetch_rows = fetch_rows if fetch_rows is not None else _rows()
        self._fetch_error = fetch_error
        self.search_calls: list[str] = []

        self.detail_renders: list[str] = []

    async def fetch_items(self, search: str = "") -> list[dict]:
        self.search_calls.append(search)
        if self._fetch_error:
            raise RuntimeError(self._fetch_error)
        return list(self._fetch_rows)

    def render_row(self, item: dict, width: int) -> str:
        return str(item.get("name", ""))

    def render_detail(self, item: dict) -> str:
        text = f"DETAIL: {item.get('name', '')}\nid={item.get('id', '')}"
        self.detail_renders.append(text)
        return text

    def menu_config(self) -> tuple[str, list[tuple[str, str]]]:
        return ("owa-fake — menu", [])

    def open_browser_for(self, item: dict) -> str | None:
        return item.get("url")


def _make_app(**screen_kw: Any) -> App:
    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(_FakeListScreen(**screen_kw))

    return _TestApp()


# --- rendering / preloaded ------------------------------------------------


def test_preloaded_items_render() -> None:
    async def _run() -> int:
        app = _make_app(initial_items=_rows(4), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(ListItem)))

    assert asyncio.run(_run()) >= 4


def test_detail_pane_right_mounts_pane() -> None:
    async def _run() -> int:
        app = _make_app(initial_items=_rows(), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) >= 1


def test_detail_pane_off_no_pane() -> None:
    async def _run() -> int:
        app = _make_app(initial_items=_rows(), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) == 0


def test_bottom_layout_mounts_pane() -> None:
    async def _run() -> int:
        app = _make_app(initial_items=_rows(), detail_pane_mode="bottom")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(_DetailPane)))

    assert asyncio.run(_run()) >= 1


# --- fetch worker ---------------------------------------------------------


def test_fetch_worker_populates_list_and_status() -> None:
    async def _run() -> tuple[int, str, list[str]]:
        app = _make_app(fetch_rows=_rows(3), detail_pane_mode="off")  # no initial_items -> fetch
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc = app.screen
            return len(sc._items), sc._status, sc.search_calls

    n, status, calls = asyncio.run(_run())
    assert n == 3
    assert status == "3 items"
    assert calls == [""]


def test_fetch_worker_empty_result() -> None:
    async def _run() -> str:
        app = _make_app(fetch_rows=[], detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return app.screen._status

    assert asyncio.run(_run()) == "0 items"


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        app = _make_app(fetch_error="network down", detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            return app.screen._status

    assert asyncio.run(_run()).startswith("error: network down")


# --- selection / detail ---------------------------------------------------


def test_highlight_updates_detail_pane() -> None:
    async def _run() -> list[str]:
        app = _make_app(initial_items=_rows(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")  # highlight first row -> auto-preview in pane
            await pilot.pause(0.1)
            return list(app.screen.detail_renders)

    renders = asyncio.run(_run())
    assert any("DETAIL: Row" in r for r in renders)


def test_open_item_switches_to_detail_mode() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("l")  # open
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "detail"


def test_open_item_off_mode_pushes_full_detail() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("l")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    # off-mode opens a full-screen detail Screen on top
    assert asyncio.run(_run()) == "_FullDetailScreen"


def test_close_detail_returns_to_list_mode() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("l")
            await pilot.press("h")  # close
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "list"


# --- navigation -----------------------------------------------------------


def test_go_bottom_then_top() -> None:
    async def _run() -> tuple[int, int]:
        app = _make_app(initial_items=_rows(5), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("G")
            await pilot.pause(0.05)
            bottom = app.screen._selected_idx
            await pilot.press("g")
            await pilot.pause(0.05)
            top = app.screen._selected_idx
            return bottom, top

    bottom, top = asyncio.run(_run())
    assert bottom == 4
    assert top == 0


# --- search ---------------------------------------------------------------


def test_search_key_opens_modal() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("/")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "_SearchModal"


def test_on_search_query_triggers_fetch_with_query() -> None:
    async def _run() -> list[str]:
        app = _make_app(fetch_rows=_rows(2), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)
            sc = app.screen
            sc.on_search_query("alice")
            await pilot.pause(0.3)
            return sc.search_calls

    calls = asyncio.run(_run())
    assert "alice" in calls
    assert calls[-1] == "alice"


# --- menu -----------------------------------------------------------------


def test_escape_opens_settings_overlay() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "SettingsOverlay"


def test_handle_menu_help_sets_status() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            app.screen.handle_menu_result("help")
            await pilot.pause(0.05)
            return app.screen._status

    assert "search" in asyncio.run(_run())


def test_handle_menu_resume_is_noop() -> None:
    sc = _FakeListScreen(initial_items=_rows(3))
    sc._status = "kept"
    sc.handle_menu_result("resume")
    assert sc._status == "kept"


# --- browser action -------------------------------------------------------


def test_open_browser_no_link_sets_status() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("o")  # no 'url' key on fake rows
            await pilot.pause(0.05)
            return app.screen._status

    assert "no browser link" in asyncio.run(_run())


def test_open_browser_with_link_calls_webbrowser() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=[{"id": "x", "name": "X", "url": "https://e.x"}])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            with patch("owa_tui.screens.base.screen.webbrowser.open") as m:
                await pilot.press("o")
                await pilot.pause(0.05)
                called = m.called
        return "ok" if called else "no"

    assert asyncio.run(_run()) == "ok"


# --- abstract-hook enforcement -------------------------------------------


def test_base_hooks_raise_not_implemented() -> None:
    bare = OwaListScreen()
    for call in (
        lambda: bare.render_row({}, 80),
        lambda: bare.render_detail({}),
        bare.menu_config,
    ):
        try:
            call()
            raise AssertionError("expected NotImplementedError")
        except NotImplementedError:
            pass


def test_base_fetch_items_raises_not_implemented() -> None:
    bare = OwaListScreen()
    try:
        asyncio.run(bare.fetch_items(""))
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError:
        pass


def test_sort_items_default_identity() -> None:
    sc = _FakeListScreen(initial_items=_rows(3))
    rows = _rows(3)
    assert sc.sort_items(rows) == rows


# --- more actions: refresh, paging, focus, cancel, scroll -----------------


def test_refresh_refetches() -> None:
    async def _run() -> list[str]:
        app = _make_app(fetch_rows=_rows(2), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)  # initial fetch ("")
            await pilot.press("r")  # refresh
            await pilot.pause(0.3)
            return app.screen.search_calls

    calls = asyncio.run(_run())
    assert len(calls) >= 2  # initial + refresh


def test_page_and_focus_keys_do_not_crash() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(8), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            for key in ("d", "u", "tab", "tab"):  # page-down, page-up, focus toggle x2
                await pilot.press(key)
                await pilot.pause(0.05)
            return app.screen._mode

    assert asyncio.run(_run()) == "list"


def test_search_modal_cancel_returns_without_fetch() -> None:
    async def _run() -> tuple[str, list[str]]:
        app = _make_app(initial_items=_rows(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("/")
            await pilot.pause(0.1)
            await pilot.press("escape")  # cancel modal
            await pilot.pause(0.1)
            sc = app.screen
            return type(sc).__name__, sc.search_calls

    name, calls = asyncio.run(_run())
    assert name == "_FakeListScreen"  # back on the list screen
    assert calls == []  # preloaded -> no fetch ever triggered


def test_full_detail_screen_scroll_and_pop() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=_rows(3), detail_pane_mode="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("l")  # opens _FullDetailScreen
            await pilot.pause(0.1)
            for key in ("j", "k", "space", "g", "G"):  # scroll actions
                await pilot.press(key)
                await pilot.pause(0.02)
            await pilot.press("escape")  # pop back to list
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "_FakeListScreen"


def test_open_item_with_no_selection_is_noop() -> None:
    async def _run() -> str:
        app = _make_app(initial_items=[], detail_pane_mode="right")  # empty list
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("l")  # nothing selected -> no-op
            await pilot.pause(0.1)
            return app.screen._mode

    assert asyncio.run(_run()) == "list"
