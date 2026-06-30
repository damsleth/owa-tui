"""Esc on the people screen: back to list when a detail is shown, else menu."""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.people.settings import PeopleSettings
from owa_tui.screens.people import PeopleScreen

_PEOPLE = [{"id": f"p{i}", "displayName": f"Person {i}", "email": f"p{i}@x.com"} for i in range(3)]


def _make_app(detail_pane="right"):
    settings = PeopleSettings(detail_pane=detail_pane)

    class _TestApp(App):
        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(
                PeopleScreen(initial_people=_PEOPLE, initial_settings=settings)
            )

    return _TestApp()


def test_escape_returns_to_list_when_detail_shown() -> None:
    async def _run() -> str:
        app = _make_app(detail_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen.mode = "detail"
            screen.action_escape()
            await pilot.pause(0.05)
            return screen.mode

    assert asyncio.run(_run()) == "list"


def test_escape_opens_menu_when_in_list() -> None:
    async def _run() -> bool:
        app = _make_app(detail_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen.mode = "list"
            before = len(app.screen_stack)
            screen.action_escape()
            await pilot.pause(0.1)
            return len(app.screen_stack) > before  # menu overlay pushed

    assert asyncio.run(_run()) is True
