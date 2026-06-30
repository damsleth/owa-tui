"""Tests for the mail TUI todo fixes:

  - toggle-read keeps the email selected (no deselect on rebuild)
  - ReaderPane j/k/u/d scroll the pane when focused
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.mail.settings import MailSettings
from owa_tui.screens.mail import MailScreen, ReaderPane


def _msgs(n: int = 6) -> list[dict]:
    return [
        {
            "id": f"m{i}",
            "received": f"2026-05-{10 + i:02d}T09:00:00Z",
            "from": f"user{i}@example.com",
            "subject": f"Subject {i}",
            "is_read": i % 2 == 0,
            "body": "x\n" * 200,  # tall body so the reader pane can scroll
            "body_type": "text",
        }
        for i in range(n)
    ]


def _make_app(messages, reading_pane="off", sort_by="date_desc"):
    settings = MailSettings(reading_pane=reading_pane, sort_by=sort_by)

    class _TestApp(App):
        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(
                MailScreen(initial_messages=messages, initial_settings=settings)
            )

    return _TestApp()


def test_toggle_read_keeps_selection_when_reordered() -> None:
    """Toggling read with unread_first sort moves the row but keeps it selected."""

    async def _run() -> tuple[str, str]:
        app = _make_app(_msgs(6), sort_by="unread_first")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            # Select the first row (an unread message, since unread sorts first).
            screen.selected = 0
            await pilot.pause(0.05)
            before = screen._current_msg()["id"]
            screen.action_toggle_read()
            await pilot.pause(0.05)
            after = screen._current_msg()["id"]
            return before, after

    before, after = asyncio.run(_run())
    assert after == before  # same email still selected after the reorder


def test_reader_pane_scroll_keys() -> None:
    """j and d scroll the focused reader pane down."""

    async def _run() -> tuple[float, float, float]:
        app = _make_app(_msgs(3), reading_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            pane = screen.query_one(ReaderPane)
            pane.show_message(_msgs(3)[0])  # tall body so the pane can scroll
            pane.focus()
            await pilot.pause(0.05)
            start = pane.scroll_offset.y
            pane.action_scroll_line_down()
            await pilot.pause(0.05)
            after_line = pane.scroll_offset.y
            pane.action_scroll_half_down()
            await pilot.pause(0.05)
            after_half = pane.scroll_offset.y
            return start, after_line, after_half

    start, after_line, after_half = asyncio.run(_run())
    assert after_line > start
    assert after_half > after_line
