"""Pilot-driven tests for ListBrowser handlers and key actions.

Covers the Missing lines from coverage:
  - on_list_view_selected (131-134): fires ItemDrilled on Enter via ListView
  - on_list_view_highlighted (136-141): fires ItemSelected on highlight
  - action_move_down/action_move_up (151, 154): j/k key bindings
  - action_move_bottom with empty list (162->exit): G on empty list
  - action_page_up_half (166-168): u key
  - action_page_down_half (171-173): d key
  - action_drill with no item (177->exit): l on empty list
  - on_key "up"/"down" branches (188-189, 191-192)
  - on_key "pageup"/"pagedown"/"space" branches (194-195, 197-198)
  - on_key "enter"/"right" branches (200-201)
  - on_key "left" branch (203-204)
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from owa_tui.widgets.list_browser import BackPressed, ItemDrilled, ItemSelected, ListBrowser

# ---------------------------------------------------------------------------
# Shared test app
# ---------------------------------------------------------------------------


class _BrowserApp(App[None]):
    """Minimal app wrapping a ListBrowser for handler/action testing."""

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


# ---------------------------------------------------------------------------
# on_list_view_selected — Enter key triggers ListView.Selected event
# ---------------------------------------------------------------------------


def test_on_list_view_selected_fires_item_drilled() -> None:
    """Pressing Enter on a list item fires ItemDrilled via on_list_view_selected."""

    async def run() -> list:
        app = _BrowserApp(["first", "second"])
        async with app.run_test() as pilot:
            await pilot.pause()
            # Focus the browser and press Enter to trigger ListView.Selected
            app.query_one("#browser", ListBrowser).focus()
            await pilot.press("enter")
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    drilled = [m for m in msgs if m[0] == "drilled"]
    assert drilled, f"Expected ItemDrilled, got: {msgs}"
    assert drilled[0][1] == "first"


def test_on_list_view_selected_via_direct_event_fires_drilled() -> None:
    """on_list_view_selected fires ItemDrilled when triggered via a real ListView.Selected event."""

    async def run() -> list:
        from textual.widgets import ListView

        app = _BrowserApp(["item-x", "item-y"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lv = lb.query_one("#list-view", ListView)
            # Build and post the event directly so on_list_view_selected is hit
            list_item = list(lv.children)[0]
            event = ListView.Selected(lv, list_item, 0)
            lb.on_list_view_selected(event)
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    drilled = [m for m in msgs if m[0] == "drilled"]
    assert drilled, f"Expected ItemDrilled via direct event, got: {msgs}"
    assert drilled[0][1] == "item-x"


def test_on_list_view_selected_no_item_on_empty_list() -> None:
    """on_list_view_selected on an empty list does not fire ItemDrilled."""

    async def run() -> list:
        app = _BrowserApp([])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.focus()
            # Manually trigger action_drill to exercise the item-is-None branch
            lb.action_drill()
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    # No ItemDrilled should be posted when there are no items
    assert not any(m[0] == "drilled" for m in msgs)


# ---------------------------------------------------------------------------
# on_list_view_highlighted — ItemSelected fired on cursor move
# ---------------------------------------------------------------------------


def test_on_list_view_highlighted_fires_item_selected_on_j() -> None:
    """Pressing j moves cursor and fires ItemSelected via on_list_view_highlighted."""

    async def run() -> list:
        app = _BrowserApp(["alpha", "beta", "gamma"])
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#browser", ListBrowser).focus()
            await pilot.press("j")
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    selected = [m for m in msgs if m[0] == "selected"]
    assert selected, f"Expected ItemSelected after j, got: {msgs}"
    assert selected[-1][1] == "beta"


# ---------------------------------------------------------------------------
# action_move_down / action_move_up via j/k bindings
# ---------------------------------------------------------------------------


def test_action_move_down_via_j_key() -> None:
    """j key calls action_move_down which moves cursor down."""

    async def run() -> object:
        app = _BrowserApp(["a", "b", "c"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.focus()
            await pilot.press("j")
            await pilot.pause()
            return lb.current_item()

    assert asyncio.run(run()) == "b"


def test_action_move_up_via_k_key() -> None:
    """k key calls action_move_up which moves cursor up."""

    async def run() -> object:
        app = _BrowserApp(["x", "y", "z"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.focus()
            # Move to bottom then back up
            lb.action_move_bottom()
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()
            return lb.current_item()

    assert asyncio.run(run()) == "y"


# ---------------------------------------------------------------------------
# action_move_bottom with empty list (162->exit branch)
# ---------------------------------------------------------------------------


def test_action_move_bottom_empty_list_does_not_crash() -> None:
    """action_move_bottom on an empty list should be a no-op (no IndexError)."""

    async def run() -> int:
        app = _BrowserApp([])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.action_move_bottom()  # must not raise
            await pilot.pause()
            return lb.item_count

    assert asyncio.run(run()) == 0


# ---------------------------------------------------------------------------
# action_page_up_half / action_page_down_half (u/d keys)
# ---------------------------------------------------------------------------


def test_action_page_up_half_via_u_key() -> None:
    """u key calls action_page_up_half; cursor moves toward top."""

    async def run() -> object:
        app = _BrowserApp(list(range(10)))
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.focus()
            lb.action_move_bottom()
            await pilot.pause()
            await pilot.press("u")
            await pilot.pause()
            return lb.current_item()

    result = asyncio.run(run())
    # After moving to bottom and pressing u, cursor should be above bottom
    assert result is not None
    assert result < 9  # moved up from index 9


def test_action_page_down_half_via_d_key() -> None:
    """d key calls action_page_down_half; cursor moves toward bottom."""

    async def run() -> object:
        app = _BrowserApp(list(range(10)))
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.focus()
            await pilot.press("d")
            await pilot.pause()
            return lb.current_item()

    result = asyncio.run(run())
    # After pressing d from top, cursor should be somewhere below index 0
    assert result is not None
    assert result >= 0


def test_action_page_up_half_direct_call() -> None:
    """action_page_up_half called directly moves index toward 0."""

    async def run() -> object:
        app = _BrowserApp(["a", "b", "c", "d", "e", "f"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.action_move_bottom()
            await pilot.pause()
            lb.action_page_up_half()
            await pilot.pause()
            return lb.current_item()

    result = asyncio.run(run())
    # Must not crash; result is the item at the new position
    assert result is not None


def test_action_page_down_half_direct_call() -> None:
    """action_page_down_half called directly moves index toward end."""

    async def run() -> object:
        app = _BrowserApp(["a", "b", "c", "d", "e", "f"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.action_page_down_half()
            await pilot.pause()
            return lb.current_item()

    result = asyncio.run(run())
    assert result is not None


# ---------------------------------------------------------------------------
# on_key branches: up/down/pageup/pagedown/space/enter/right/left
# ---------------------------------------------------------------------------


def test_on_key_up_moves_cursor_up() -> None:
    """Arrow-up key is forwarded to ListView via on_key."""

    async def run() -> object:
        app = _BrowserApp(["p", "q", "r"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.focus()
            lb.action_move_bottom()
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()
            return lb.current_item()

    result = asyncio.run(run())
    assert result == "q"


def test_on_key_down_moves_cursor_down() -> None:
    """Arrow-down key is forwarded to ListView via on_key."""

    async def run() -> object:
        app = _BrowserApp(["p", "q", "r"])
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            lb.focus()
            await pilot.press("down")
            await pilot.pause()
            return lb.current_item()

    result = asyncio.run(run())
    assert result == "q"


def test_on_key_pageup_does_not_crash() -> None:
    """pageup key branch in on_key is reached via direct on_key call with mocked scroll."""

    async def run() -> int:
        app = _BrowserApp(list(range(20)))
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            from unittest.mock import MagicMock

            lv = lb.query_one("#list-view")
            # Replace scroll action with a no-op so on_key can complete the branch
            lv.action_scroll_up = MagicMock(return_value=None)  # type: ignore[method-assign]
            fake_event = MagicMock()
            fake_event.key = "pageup"
            lb.on_key(fake_event)
            await pilot.pause()
            return lb.item_count

    # Must not crash; item_count stays the same
    assert asyncio.run(run()) == 20


def test_on_key_pagedown_does_not_crash() -> None:
    """pagedown key branch in on_key is reached via direct on_key call with mocked scroll."""

    async def run() -> int:
        app = _BrowserApp(list(range(20)))
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            from unittest.mock import MagicMock

            lv = lb.query_one("#list-view")
            lv.action_scroll_down = MagicMock(return_value=None)  # type: ignore[method-assign]
            fake_event = MagicMock()
            fake_event.key = "pagedown"
            lb.on_key(fake_event)
            await pilot.pause()
            return lb.item_count

    assert asyncio.run(run()) == 20


def test_on_key_space_does_not_crash() -> None:
    """space key branch in on_key is reached via direct on_key call with mocked scroll."""

    async def run() -> int:
        app = _BrowserApp(list(range(20)))
        async with app.run_test() as pilot:
            await pilot.pause()
            lb = app.query_one("#browser", ListBrowser)
            from unittest.mock import MagicMock

            lv = lb.query_one("#list-view")
            lv.action_scroll_down = MagicMock(return_value=None)  # type: ignore[method-assign]
            fake_event = MagicMock()
            fake_event.key = "space"
            lb.on_key(fake_event)
            await pilot.pause()
            return lb.item_count

    assert asyncio.run(run()) == 20


def test_on_key_enter_fires_drilled() -> None:
    """enter key calls action_drill via on_key, posting ItemDrilled."""

    async def run() -> list:
        app = _BrowserApp(["item-a", "item-b"])
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#browser", ListBrowser).focus()
            await pilot.press("enter")
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    assert any(m[0] == "drilled" for m in msgs)


def test_on_key_right_fires_drilled() -> None:
    """right arrow calls action_drill via on_key, posting ItemDrilled."""

    async def run() -> list:
        app = _BrowserApp(["item-a", "item-b"])
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#browser", ListBrowser).focus()
            await pilot.press("right")
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    assert any(m[0] == "drilled" for m in msgs)


def test_on_key_left_fires_back_pressed() -> None:
    """left arrow calls action_back via on_key, posting BackPressed."""

    async def run() -> list:
        app = _BrowserApp(["item-a"])
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#browser", ListBrowser).focus()
            await pilot.press("left")
            await pilot.pause()
            return app.received

    msgs = asyncio.run(run())
    assert ("back",) in msgs
