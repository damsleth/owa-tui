"""Pilot tests for ListBrowser widget."""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from owa_tui.widgets.list_browser import BackPressed, ItemDrilled, ItemSelected, ListBrowser


class _BrowserApp(App[None]):
    """Minimal app wrapping a ListBrowser for testing."""

    def __init__(self, items: list) -> None:
        super().__init__()
        self._items = items
        self.received: list = []

    def compose(self) -> ComposeResult:
        yield ListBrowser(self._items, id="browser")

    def on_item_selected(self, event: ItemSelected) -> None:
        self.received.append(("selected", event.item))

    def on_item_drilled(self, event: ItemDrilled) -> None:
        self.received.append(("drilled", event.item))

    def on_back_pressed(self, event: BackPressed) -> None:
        self.received.append(("back",))


def test_list_browser_item_count() -> None:
    """ListBrowser should expose item_count after update_rows."""

    async def run() -> int:
        app = _BrowserApp(["a", "b", "c"])
        async with app.run_test() as pilot:
            await pilot.pause()
            return app.query_one("#browser", ListBrowser).item_count

    assert asyncio.run(run()) == 3


def test_list_browser_current_item() -> None:
    """current_item() returns the first item when at index 0."""

    async def run() -> object:
        app = _BrowserApp(["alpha", "beta"])
        async with app.run_test() as pilot:
            await pilot.pause()
            return app.query_one("#browser", ListBrowser).current_item()

    assert asyncio.run(run()) == "alpha"


def test_list_browser_update_rows() -> None:
    """update_rows() replaces items and updates item_count."""

    async def run() -> int:
        app = _BrowserApp(["x"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.update_rows(["a", "b", "c", "d"])
            await pilot.pause()
            return lb.item_count

    assert asyncio.run(run()) == 4


def test_list_browser_empty_list() -> None:
    """ListBrowser with empty items has item_count 0 and current_item None."""

    async def run() -> tuple:
        app = _BrowserApp([])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            return lb.item_count, lb.current_item()

    count, item = asyncio.run(run())
    assert count == 0
    assert item is None


def test_list_browser_render_item_default() -> None:
    """Default render_item returns str(item)."""
    lb = ListBrowser()
    assert lb.render_item(42) == "42"
    assert lb.render_item("hello") == "hello"


def test_list_browser_render_item_override() -> None:
    """Subclass can override render_item."""

    class MyBrowser(ListBrowser):
        def render_item(self, item: object) -> str:
            return f"[{item}]"

    mb = MyBrowser()
    assert mb.render_item("x") == "[x]"


def test_list_browser_action_back_fires_message() -> None:
    """Pressing 'h' fires BackPressed message."""

    async def run() -> list:
        app = _BrowserApp(["a", "b"])
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    assert ("back",) in msgs


def test_list_browser_action_drill_fires_message() -> None:
    """Pressing 'l' fires ItemDrilled message."""

    async def run() -> list:
        app = _BrowserApp(["item-one", "item-two"])
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("l")
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    assert any(m[0] == "drilled" for m in msgs)


def test_list_browser_move_top_bottom() -> None:
    """'G' moves to last item; 'g' moves back to first."""

    async def run() -> tuple:
        app = _BrowserApp(["a", "b", "c"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.action_move_bottom()
            await pilot.pause()
            bottom_item = lb.current_item()
            lb.action_move_top()
            await pilot.pause()
            top_item = lb.current_item()
            return bottom_item, top_item

    bottom, top = asyncio.run(run())
    assert bottom == "c"
    assert top == "a"
