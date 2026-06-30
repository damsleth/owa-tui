"""Settings changes apply to the layout immediately (no screen re-entry)."""

from __future__ import annotations

import asyncio
import dataclasses

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.mail.settings import MailSettings
from owa_tui.screens.mail import MailScreen, ReaderPane


def _msgs(n: int) -> list[dict]:
    return [{"id": f"m{i}", "received": f"2026-05-{10 + i:02d}T09:00:00Z",
             "from": f"u{i}@x.com", "subject": f"S{i}", "is_read": True} for i in range(n)]


def _make_app(reading_pane="right", split_ratio=50):
    settings = MailSettings(reading_pane=reading_pane, split_ratio=split_ratio)

    class _TestApp(App):
        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(MailScreen(initial_messages=_msgs(5), initial_settings=settings))

    return _TestApp()


def test_reading_pane_change_rebuilds_layout_and_keeps_selection() -> None:
    async def _run():
        app = _make_app(reading_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            screen.selected = 3
            await pilot.pause(0.05)
            has_reader_right = bool(list(screen.query(ReaderPane)))

            screen._apply_settings(dataclasses.replace(screen.settings, reading_pane="off"))
            await pilot.pause(0.1)
            has_reader_off = bool(list(screen.query(ReaderPane)))
            sel_after_off = screen.selected

            screen._apply_settings(dataclasses.replace(screen.settings, reading_pane="bottom"))
            await pilot.pause(0.1)
            has_reader_bottom = bool(list(screen.query(ReaderPane)))
            return has_reader_right, has_reader_off, has_reader_bottom, sel_after_off

    right, off, bottom, sel = asyncio.run(_run())
    assert right is True
    assert off is False  # pane removed live
    assert bottom is True  # pane re-added live
    assert sel == 3  # selection survived the rebuild


def test_split_ratio_applies_in_place() -> None:
    async def _run():
        app = _make_app(reading_pane="right", split_ratio=50)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            screen._apply_settings(dataclasses.replace(screen.settings, split_ratio=60))
            await pilot.pause(0.05)
            ml = screen._message_list()
            return str(ml.styles.width)

    assert "60" in asyncio.run(_run())
