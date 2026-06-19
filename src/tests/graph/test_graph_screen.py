"""Pilot tests for GraphScreen: TP49–TP56."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

# Ensure the graph screen module is imported so register_screen() runs
import owa_tui.screens.graph  # noqa: F401

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(audience: str = "graph") -> object:
    import owa_tui

    # Patch fetch so the screen doesn't make network calls
    return owa_tui.OwaTuiApp(config={}, tool="graph")


def _get_graph_screen(app: object) -> object:
    """Find the GraphScreen in the screen stack (it may not be the top)."""
    from owa_tui.screens.graph import GraphScreen

    for screen in getattr(app, "screen_stack", []):
        if isinstance(screen, GraphScreen):
            return screen
    # Fallback: return top screen
    return getattr(app, "screen", None)


def _noop_fetch(state: object) -> None:
    """Replacement for fetch_items that sets no items (offline stub)."""
    from owa_tui.graph.state import GraphState

    if isinstance(state, GraphState):
        state.items = []
        state.status = "offline (test)"
        state.dirty = False


# ---------------------------------------------------------------------------
# TP49: graph screen mounts without crashing
# ---------------------------------------------------------------------------


def test_graph_screen_mounts() -> None:
    """TP49: GraphScreen mounts cleanly with no config (offline)."""

    async def _run() -> str:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_noop_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                # Screen stack should include GraphScreen
                screen_names = [type(s).__name__ for s in app.screen_stack]
                return ",".join(screen_names)

    result = asyncio.run(_run())
    assert "GraphScreen" in result


# ---------------------------------------------------------------------------
# TP50: breadcrumb shows current audience:path
# ---------------------------------------------------------------------------


def test_graph_screen_breadcrumb() -> None:
    """TP50: breadcrumb label shows 'graph:me' on initial mount."""
    from textual.widgets import Static

    async def _run() -> str:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_noop_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                breadcrumb = app.screen.query_one("#breadcrumb", Static)
                return str(breadcrumb.render())

    result = asyncio.run(_run())
    assert "graph" in result


# ---------------------------------------------------------------------------
# TP51: status bar is present
# ---------------------------------------------------------------------------


def test_graph_screen_status_bar_present() -> None:
    """TP51: status-bar widget is present and visible."""
    from textual.widgets import Static

    async def _run() -> bool:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_noop_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                try:
                    app.screen.query_one("#status-bar", Static)
                    return True
                except Exception:
                    return False

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# TP52: list view is present
# ---------------------------------------------------------------------------


def test_graph_screen_list_view_present() -> None:
    """TP52: #graph-list ListView is present."""
    from textual.widgets import ListView

    async def _run() -> bool:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_noop_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                try:
                    app.screen.query_one("#graph-list", ListView)
                    return True
                except Exception:
                    return False

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# TP53: q key quits the app
# ---------------------------------------------------------------------------


def test_quit_terminates_app() -> None:
    """TP53: pressing q exits the app."""

    async def _run() -> bool:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_noop_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                await pilot.press("q")
                await pilot.pause(0.1)
                return not app.is_running

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# TP54: r key triggers a re-fetch
# ---------------------------------------------------------------------------


def test_refresh_key_triggers_fetch() -> None:
    """TP54: pressing r increments fetch call count."""
    fetch_calls: list[int] = [0]

    def _counting_fetch(state: object) -> None:
        _noop_fetch(state)
        fetch_calls[0] += 1

    async def _run() -> int:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_counting_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.2)
                initial = fetch_calls[0]
                await pilot.press("r")
                await pilot.pause(0.3)
                return fetch_calls[0] - initial

    delta = asyncio.run(_run())
    assert delta >= 1


# ---------------------------------------------------------------------------
# TP55: D key toggles debug overlay
# ---------------------------------------------------------------------------


def test_debug_overlay_toggle() -> None:
    """TP55: pressing D toggles the debug overlay visibility."""
    from textual.widgets import Static

    async def _run() -> tuple[bool, bool]:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_noop_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                overlay = app.screen.query_one("#debug-overlay", Static)
                before = "visible" in overlay.classes
                await pilot.press("D")
                await pilot.pause(0.05)
                after = "visible" in overlay.classes
                return before, after

    before, after = asyncio.run(_run())
    assert before is False
    assert after is True


# ---------------------------------------------------------------------------
# TP56: resize does not crash
# ---------------------------------------------------------------------------


def test_resize_does_not_crash() -> None:
    """TP56: sending a resize (Size) message doesn't crash the app."""

    async def _run() -> bool:
        with patch("owa_tui.screens.graph.fetch_items", side_effect=_noop_fetch):
            app = _make_app()
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                # Simulate resize by setting terminal size
                await pilot.resize_terminal(100, 40)
                await pilot.pause(0.1)
                return app.is_running

    assert asyncio.run(_run())
