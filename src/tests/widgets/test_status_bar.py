"""StatusBar overlays AppHeader row 3, hides when empty, auto-clears."""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from owa_tui.widgets.app_header import AppHeader
from owa_tui.widgets.status_bar import StatusBar


class _App(App):
    CSS_PATH = "../../owa_tui/widgets/base.tcss"

    def compose(self) -> ComposeResult:
        yield AppHeader()
        yield StatusBar("Loading…", id="status-bar")


def test_status_bar_overlays_header_row_and_hides_when_empty() -> None:
    async def _run() -> list:
        out = []
        app = _App()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            bar = app.query_one(StatusBar)
            out.append((bar.display, bar.region.y, bar.region.height))
            bar.update("")
            await pilot.pause()
            out.append(bar.display)
            bar.update("3 messages")
            await pilot.pause()
            out.append((bar.display, bar.region.y))
        return out

    first, hidden, again = asyncio.run(_run())
    assert first == (True, 2, 1)  # initial text shows on header row 3
    assert hidden is False  # empty → identity row shows through
    assert again == (True, 2)


def test_status_bar_auto_clears_and_new_message_resets_timer(monkeypatch) -> None:
    monkeypatch.setattr(StatusBar, "AUTO_CLEAR", 0.6)

    async def _run() -> list:
        out = []
        app = _App()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            bar = app.query_one(StatusBar)
            await pilot.pause(0.3)
            bar.update("3 messages")  # arrives before "Loading…" would clear
            await pilot.pause(0.3)
            out.append((bar.display, str(bar.content)))  # old timer cancelled
            await pilot.pause(0.6)
            out.append((bar.display, str(bar.content)))  # new timer fired
        return out

    assert asyncio.run(_run()) == [(True, "3 messages"), (False, "")]
