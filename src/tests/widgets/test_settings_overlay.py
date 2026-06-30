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


def test_settings_overlay_background_is_opaque() -> None:
    """Background must be fully opaque so the list behind (incl. emoji) can't
    show through the menu — the default ModalScreen is 60% alpha."""

    async def run() -> float:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            return app.screen.styles.background.a

    assert asyncio.run(run()) == 1.0


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


def test_settings_overlay_cycle_bool_field_in_place() -> None:
    """Enter on a bool field toggles it in place without closing the menu."""

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
            # Enter on the field cycles it in place (no dismiss)
            await pilot.press("enter")
            await pilot.pause()
            return app.result, app._settings.show_declined

    result, val = asyncio.run(run())
    assert result is None  # menu stayed open
    assert val is True  # was False, now toggled


def test_settings_overlay_shows_value_next_to_label() -> None:
    """Settings rows render as ``label: value`` from the live settings object."""

    async def run() -> list[str]:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            await pilot.press("j")  # → Settings
            await pilot.press("enter")  # open sub-menu
            await pilot.pause()
            from textual.widgets import Static

            return [str(app.screen.query_one("#menu-items", Static).render())]

    rendered = asyncio.run(run())[0]
    assert "Show declined: False" in rendered


def test_settings_overlay_space_and_arrows_cycle() -> None:
    """space / l / right / h / left all cycle the field in place."""

    async def run() -> bool:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            await pilot.press("j", "enter")  # → Settings sub-menu
            await pilot.pause()
            await pilot.press("space")  # toggle True
            await pilot.press("l")      # toggle False
            await pilot.press("right")  # toggle True
            await pilot.press("h")      # toggle False
            await pilot.press("left")   # toggle True
            await pilot.pause()
            return app._settings.show_declined

    assert asyncio.run(run()) is True  # odd number of toggles from False


def test_settings_overlay_on_change_called_live() -> None:
    """on_change fires on every cycle while the menu stays open."""
    changes: list[tuple[str, bool]] = []

    @dataclass
    class S:
        flag: bool = False

    class _App(App[None]):
        def compose(self) -> ComposeResult:
            yield Label("host")

        def show(self) -> None:
            self.push_screen(
                SettingsOverlay(
                    title_lines=["T"],
                    top_items=[("Resume", "resume"), ("Settings", "settings")],
                    settings_fields=[("flag", "Flag")],
                    settings=S(),
                    cycle_fn=lambda s, f, d: S(flag=not s.flag),
                    on_change=lambda f, s: changes.append((f, s.flag)),
                )
            )

    async def run() -> None:
        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show()
            await pilot.pause()
            await pilot.press("j", "enter")  # → Settings
            await pilot.press("l", "l")      # two cycles
            await pilot.pause()

    asyncio.run(run())
    assert changes == [("flag", True), ("flag", False)]


def test_settings_overlay_action_field_dismisses() -> None:
    """A ``_``-prefixed field is a plain action: Enter dismisses with the name."""

    class _App(App[None]):
        def compose(self) -> ComposeResult:
            yield Label("host")
            self.result: str | None = None

        def show(self) -> None:
            self.push_screen(
                SettingsOverlay(
                    title_lines=["T"],
                    top_items=[("Resume", "resume"), ("Settings", "settings")],
                    settings_fields=[("_reset", "Reset to defaults")],
                ),
                lambda r: setattr(self, "result", r),
            )

    async def run() -> str | None:
        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show()
            await pilot.pause()
            await pilot.press("j", "enter")  # → Settings sub-menu
            await pilot.press("enter")       # activate _reset
            await pilot.pause()
            return app.result

    assert asyncio.run(run()) == "reset"
