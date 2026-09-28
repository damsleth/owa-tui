"""Pilot tests for SettingsOverlay modal screen."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from textual.app import App, ComposeResult
from textual.color import Color
from textual.widgets import Label

import owa_tui
from owa_tui.widgets.settings_overlay import SettingsOverlay


@dataclass
class FakeSettings:
    show_declined: bool = False


class _OverlayApp(App[None]):
    """Host app that can push a SettingsOverlay and capture the result."""

    # Load the real app stylesheet so tests catch base.tcss shadowing DEFAULT_CSS.
    CSS_PATH = str(Path(owa_tui.__file__).parent / "widgets" / "base.tcss")

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
            # Items: Resume, Settings, Switch profile (auto-inserted), Quit
            await pilot.press("j", "j", "j")
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


def test_overlay_background_follows_theme() -> None:
    """Regression: base.tcss once pinned the overlay to rgba(0,0,0,0.6),
    ignoring the theme and painting black over a transparent terminal."""

    async def run() -> None:
        app = _OverlayApp()
        async with app.run_test() as pilot:
            for theme in ("textual-light", "ansi-dark"):
                app.theme = theme
                app.show_overlay()
                await pilot.pause()
                overlay = app.screen
                assert isinstance(overlay, SettingsOverlay)
                expected = app.get_css_variables()["background"]
                # Full Color compare keeps the ansi flag: ansi_default is what makes
                # the transparent-terminal toggle work, and a plain black also hexes
                # to #000000.
                assert overlay.styles.background == Color.parse(expected)
                app.pop_screen()
                await pilot.pause()

    asyncio.run(run())


def _profiles(*aliases: str, default: str = ""):
    from types import SimpleNamespace

    return [SimpleNamespace(alias=a, registered=True, default=a == default) for a in aliases]


def test_switch_profile_item_is_inserted_before_quit() -> None:
    from owa_tui.widgets.settings_overlay import PROFILE_ITEM, _with_profile_item

    items = [("Resume", "resume"), ("Help", "help"), ("Quit", "quit")]
    assert _with_profile_item(items) == [items[0], items[1], PROFILE_ITEM, items[2]]
    assert _with_profile_item([("Resume", "resume")])[-1] == PROFILE_ITEM
    assert _with_profile_item(_with_profile_item(items)).count(PROFILE_ITEM) == 1


def test_switch_profile_picks_alias_and_calls_app(monkeypatch) -> None:
    """Switch profile → picker lists registered profiles → Enter hands the alias to the app."""
    import owa_core.auth

    monkeypatch.setattr(owa_core.auth, "get_profiles", lambda **k: _profiles("une", "nc", default="une"))
    switched: list[str] = []

    class _App(_OverlayApp):
        def switch_profile(self, alias: str) -> None:
            switched.append(alias)

    async def run() -> tuple[list[str], str | None]:
        app = _App()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.show_overlay()
            await pilot.pause()
            await pilot.press("j", "j", "enter")  # Switch profile
            await app.workers.wait_for_complete()
            await pilot.pause()
            opts = [str(o.prompt) for o in app.screen.query_one("OptionList").options]
            await pilot.press("j", "enter")  # nc
            await pilot.pause()
            await pilot.pause()
            return opts, app.result

    opts, result = asyncio.run(run())
    assert opts == ["une  (current)", "nc"]
    assert result == "resume"
    assert switched == ["nc"]


def test_app_switch_profile_rebuilds_the_open_tool_screen(monkeypatch) -> None:
    monkeypatch.setenv("OWA_TUI_FIXTURES", str(Path(owa_tui.__file__).parents[2] / "e2e" / "fixtures"))
    from owa_tui.screens.cal import CalScreen

    async def run():
        app = owa_tui.OwaTuiApp(tool="cal")
        async with app.run_test() as pilot:
            await pilot.pause()
            before = app.screen
            app.switch_profile("nc")
            await pilot.pause()
            return before, app.screen, app._config, app.sub_title, len(app.screen_stack)

    before, after, config, sub, depth = asyncio.run(run())
    assert isinstance(after, CalScreen) and after is not before
    assert config["owa_piggy_profile"] == "nc" and sub == "nc"
    assert depth == 2  # default screen + the rebuilt tool, nothing stacked twice
