"""Pilot tests for SettingsOverlay modal screen."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.widgets import Label

from owa_tui.widgets.settings_overlay import SettingsOverlay


@dataclass
class FakeSettings:
    show_declined: bool = False


class _OverlayApp(App[None]):
    """Host app that can push a SettingsOverlay and capture the result."""

    def __init__(self) -> None:
        super().__init__()
        self.result: str | None = None
        self._settings = FakeSettings()

    def compose(self) -> ComposeResult:
        yield Label("host")

    def show_overlay(self) -> None:
        overlay = SettingsOverlay(
            title_lines=["Test Overlay"],
            top_items=[("Resume", "resume"), ("Settings", "settings"), ("Quit", "quit")],
            settings_fields=[("show_declined", "Show declined")],
            settings=self._settings,
        )
        self.push_screen(overlay, self._on_result)

    def _on_result(self, result: str | None) -> None:
        self.result = result


def test_settings_overlay_mounts_and_shows_title() -> None:
    """Overlay should render the title line."""

    async def run() -> list[str]:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            # Labels live on the active modal screen
            return [str(label.render()) for label in app.screen.query(Label)]

    labels = asyncio.run(run())
    assert any("Test Overlay" in lbl for lbl in labels)


def test_settings_overlay_escape_dismisses_with_resume() -> None:
    """Pressing Escape should dismiss the overlay with 'resume'."""

    async def run() -> str | None:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            return app.result

    result = asyncio.run(run())
    assert result == "resume"


def test_settings_overlay_select_quit() -> None:
    """Navigating to Quit and pressing Enter dismisses with 'quit'."""

    async def run() -> str | None:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            # Move down twice to reach "Quit" (items: Resume, Settings, Quit)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("enter")
            await pilot.pause()
            return app.result

    result = asyncio.run(run())
    assert result == "quit"


def test_settings_overlay_enter_settings_submenu() -> None:
    """Selecting 'Settings' opens sub-menu (not dismissed yet)."""

    async def run() -> str | None:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            # Move to Settings (index 1)
            await pilot.press("j")
            await pilot.press("enter")
            await pilot.pause()
            # Should still be in overlay (not dismissed)
            # Press Escape to go back to top
            await pilot.press("escape")
            await pilot.pause()
            # Press Escape again to dismiss
            await pilot.press("escape")
            await pilot.pause()
            return app.result

    result = asyncio.run(run())
    assert result == "resume"


def test_settings_overlay_cycle_bool_field() -> None:
    """Cycling a bool settings field should toggle it."""

    async def run() -> tuple[str | None, bool]:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            # Go to Settings
            await pilot.press("j")
            await pilot.press("enter")
            await pilot.pause()
            # Select the first (only) settings field
            await pilot.press("enter")
            await pilot.pause()
            return app.result, app._settings.show_declined

    result, val = asyncio.run(run())
    assert result == "cycle:show_declined"
    assert val is True  # was False, now toggled
