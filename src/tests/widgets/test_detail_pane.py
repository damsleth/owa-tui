"""Pilot tests for DetailPane widget."""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Static

from owa_tui.widgets.detail_pane import DetailPane


class _PaneApp(App[None]):
    def compose(self) -> ComposeResult:
        yield DetailPane(id="pane")


def test_detail_pane_update_content() -> None:
    """update_content() sets the Static child text."""

    async def run() -> str:
        app = _PaneApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.query_one("#pane", DetailPane)
            pane.update_content(["Hello", "World"])
            await pilot.pause()
            return str(app.query_one("#detail-content", Static).render())

    result = asyncio.run(run())
    assert "Hello" in result
    assert "World" in result


def test_detail_pane_clear() -> None:
    """clear() empties the content."""

    async def run() -> str:
        app = _PaneApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.query_one("#pane", DetailPane)
            pane.update_content(["some text"])
            pane.clear()
            await pilot.pause()
            return str(app.query_one("#detail-content", Static).render())

    result = asyncio.run(run())
    assert result.strip() == ""


def test_detail_pane_empty_lines() -> None:
    """update_content([]) shows empty string."""

    async def run() -> str:
        app = _PaneApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.query_one("#pane", DetailPane)
            pane.update_content([])
            await pilot.pause()
            return str(app.query_one("#detail-content", Static).render())

    result = asyncio.run(run())
    assert result.strip() == ""
