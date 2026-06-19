"""Navigation tests: HomeScreen lists all three tools and push_tool works for each."""

from __future__ import annotations

import asyncio

import pytest

import owa_tui
from owa_tui.screens import SCREEN_REGISTRY, registered_tools

# ---------------------------------------------------------------------------
# Registry sanity checks (no Textual app required)
# ---------------------------------------------------------------------------


def test_registry_contains_cal() -> None:
    """CalScreen must be registered under 'cal'."""
    assert "cal" in SCREEN_REGISTRY, "CalScreen not found in SCREEN_REGISTRY"
    assert SCREEN_REGISTRY["cal"]["label"] == "Calendar"


def test_registry_contains_mail() -> None:
    """MailScreen must be registered under 'mail'."""
    assert "mail" in SCREEN_REGISTRY, "MailScreen not found in SCREEN_REGISTRY"
    assert SCREEN_REGISTRY["mail"]["label"] == "Mail"


def test_registry_contains_graph() -> None:
    """GraphScreen must be registered under 'graph'."""
    assert "graph" in SCREEN_REGISTRY, "GraphScreen not found in SCREEN_REGISTRY"
    assert SCREEN_REGISTRY["graph"]["label"] == "Graph Explorer"


def test_registered_tools_lists_all_three() -> None:
    """registered_tools() must include cal, mail, and graph."""
    keys = {k for k, _ in registered_tools()}
    assert {"cal", "mail", "graph"}.issubset(keys)


# ---------------------------------------------------------------------------
# HomeScreen Pilot tests
# ---------------------------------------------------------------------------


def test_home_screen_shows_all_three_tools() -> None:
    """HomeScreen ListView should contain list items for all three tool keys."""

    async def run() -> list[str]:
        app = owa_tui.OwaTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import ListItem

            # Collect IDs of every ListItem on the active screen
            return [item.id or "" for item in app.screen.query(ListItem)]

    item_ids = asyncio.run(run())
    assert "tool-cal" in item_ids, f"tool-cal not in {item_ids}"
    assert "tool-mail" in item_ids, f"tool-mail not in {item_ids}"
    assert "tool-graph" in item_ids, f"tool-graph not in {item_ids}"


@pytest.mark.parametrize("tool_key,expected_screen", [
    ("cal", "CalScreen"),
    ("graph", "GraphScreen"),
])
def test_push_tool_navigates_to_screen(tool_key: str, expected_screen: str) -> None:
    """push_tool(key) must push the correct screen onto the stack."""

    async def run(key: str) -> list[str]:
        app = owa_tui.OwaTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_tool(key)
            await pilot.pause()
            return [type(s).__name__ for s in app.screen_stack]

    screen_names = asyncio.run(run(tool_key))
    assert expected_screen in screen_names, (
        f"Expected {expected_screen} in screen_stack after push_tool({tool_key!r}), "
        f"got: {screen_names}"
    )


def test_push_tool_mail_pushes_mail_screen() -> None:
    """push_tool('mail') must push MailScreen; pre-load messages to avoid network I/O."""

    async def run() -> list[str]:
        from owa_tui.screens.mail import MailScreen

        app = owa_tui.OwaTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # Push MailScreen directly with pre-loaded messages to skip auth/network.
            app.push_screen(MailScreen(initial_messages=[]))
            await pilot.pause()
            return [type(s).__name__ for s in app.screen_stack]

    screen_names = asyncio.run(run())
    assert "MailScreen" in screen_names, (
        f"Expected MailScreen in screen_stack, got: {screen_names}"
    )


def test_home_screen_no_placeholder_when_tools_registered() -> None:
    """When tools are registered the 'no-tools-label' placeholder must not appear."""

    async def run() -> list[str]:
        app = owa_tui.OwaTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Label

            return [w.id or "" for w in app.screen.query(Label)]

    label_ids = asyncio.run(run())
    assert "no-tools-label" not in label_ids, (
        "Placeholder 'no-tools-label' should not appear when screens are registered"
    )
