"""Pilot tests for PeopleScreen — all 15 plan cases covered.

Tests follow the project pattern: async helpers wrapped in asyncio.run()
so plain pytest (no pytest-asyncio) can execute them.

All owa-tools / auth calls are mocked — no live Microsoft calls.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from owa_tui.people.settings import PeopleSettings
from owa_tui.screens.people import DetailPane, DetailScreen, PeopleScreen, SearchModal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _people(n: int = 6) -> list[dict]:
    return [
        {
            "id": f"p{i}",
            "displayName": f"Person {i}",
            "email": f"person{i}@example.com",
            "jobTitle": f"Title {i}",
            "department": f"Dept {i}",
            "companyName": "Example Corp",
            "officeLocation": "Oslo",
            "mobilePhone": f"+1-555-000{i}",
            "businessPhones": [],
            "source": "people",
        }
        for i in range(n)
    ]


def _make_app(
    people: list[dict] | None = None,
    detail_pane: str = "off",
    sort_by: str = "name_asc",
):
    """Create a minimal App that pushes a pre-loaded PeopleScreen."""
    from textual.app import App, ComposeResult
    from textual.widgets import Footer, Header

    settings = PeopleSettings(detail_pane=detail_pane, sort_by=sort_by)

    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            screen = PeopleScreen(
                initial_people=people if people is not None else _people(),
                initial_settings=settings,
            )
            self.push_screen(screen)

    return _TestApp()


# ---------------------------------------------------------------------------
# 1. test_screen_renders_people_list
# ---------------------------------------------------------------------------


def test_screen_renders_people_list() -> None:
    """PeopleScreen with 6 people renders all list items."""

    async def _run() -> int:
        from textual.widgets import ListItem

        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(ListItem)))

    count = asyncio.run(_run())
    assert count >= 6


# ---------------------------------------------------------------------------
# 2. test_screen_detail_pane_right_shows_pane
# ---------------------------------------------------------------------------


def test_screen_detail_pane_right_shows_pane() -> None:
    """detail_pane='right' mounts a DetailPane widget."""

    async def _run() -> int:
        app = _make_app(detail_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(DetailPane)))

    assert asyncio.run(_run()) >= 1


# ---------------------------------------------------------------------------
# 3. test_screen_detail_pane_off_no_pane_widget
# ---------------------------------------------------------------------------


def test_screen_detail_pane_off_no_pane_widget() -> None:
    """detail_pane='off' mounts no DetailPane in the DOM."""

    async def _run() -> int:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(DetailPane)))

    assert asyncio.run(_run()) == 0


# ---------------------------------------------------------------------------
# 4. test_screen_j_moves_selection_down
# ---------------------------------------------------------------------------


def test_screen_j_moves_selection_down() -> None:
    """Pressing j twice moves selected to index 2."""

    async def _run() -> int:
        app = _make_app(detail_pane="off", sort_by="name_asc")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.pause(0.05)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            return screen.selected

    assert asyncio.run(_run()) == 2


# ---------------------------------------------------------------------------
# 5. test_screen_G_jumps_to_last
# ---------------------------------------------------------------------------


def test_screen_G_jumps_to_last() -> None:
    """Pressing G with 6 people jumps to index 5."""

    async def _run() -> int:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("G")
            await pilot.pause(0.05)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            return screen.selected

    assert asyncio.run(_run()) == 5


# ---------------------------------------------------------------------------
# 6. test_screen_g_jumps_to_top
# ---------------------------------------------------------------------------


def test_screen_g_jumps_to_top() -> None:
    """Pressing g after j x3 jumps back to index 0."""

    async def _run() -> int:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("g")
            await pilot.pause(0.05)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            return screen.selected

    assert asyncio.run(_run()) == 0


# ---------------------------------------------------------------------------
# 7. test_screen_open_detail_uses_cache
# ---------------------------------------------------------------------------


def test_screen_open_detail_uses_cache() -> None:
    """When detail is in cache and pane='off', pressing enter pushes DetailScreen."""
    people = _people(1)
    pid = people[0]["id"]
    full_person = {**people[0], "jobTitle": "Lead Engineer"}

    async def _run() -> type:
        app = _make_app(people=people, detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            # Pre-populate detail cache so no live fetch needed
            screen._detail_cache[pid] = full_person
            await pilot.press("enter")
            await pilot.pause(0.1)
            return type(app.screen)

    assert asyncio.run(_run()) is DetailScreen


# ---------------------------------------------------------------------------
# 8. test_screen_open_detail_no_cache_triggers_fetch
# ---------------------------------------------------------------------------


def test_screen_open_detail_no_cache_triggers_fetch() -> None:
    """Opening a person with no cache entry triggers _fetch_detail."""
    people = _people(1)
    called: list[str] = []

    async def _run() -> list[str]:
        app = _make_app(people=people, detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with patch.object(screen, "_fetch_detail", side_effect=lambda pid: called.append(pid)):
                await pilot.press("enter")
                await pilot.pause(0.1)
        return called

    result = asyncio.run(_run())
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# 9. test_screen_body_fetch_failure_sets_status
# ---------------------------------------------------------------------------


def test_screen_body_fetch_failure_sets_status() -> None:
    """_on_detail_failed sets status to 'failed' and mode to 'list'."""

    async def _run() -> tuple[str, str]:
        app = _make_app(people=_people(1), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._on_detail_failed()
            await pilot.pause(0.05)
            return screen.status, screen.mode

    status, mode = asyncio.run(_run())
    assert "failed" in status
    assert mode == "list"


# ---------------------------------------------------------------------------
# 10. test_screen_search_modal_opens
# ---------------------------------------------------------------------------


def test_screen_search_modal_opens() -> None:
    """Pressing / opens the SearchModal."""

    async def _run() -> type:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("/")
            await pilot.pause(0.1)
            return type(app.screen)

    assert asyncio.run(_run()) is SearchModal


# ---------------------------------------------------------------------------
# 11. test_screen_escape_opens_menu
# ---------------------------------------------------------------------------


def test_screen_escape_opens_menu() -> None:
    """Pressing Escape opens the settings overlay ModalScreen."""
    from owa_tui.widgets.settings_overlay import SettingsOverlay

    async def _run() -> type:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen)

    assert asyncio.run(_run()) is SettingsOverlay


# ---------------------------------------------------------------------------
# 12. test_screen_quit_pops_screen
# ---------------------------------------------------------------------------


def test_screen_quit_pops_screen() -> None:
    """Pressing q pops the PeopleScreen."""

    async def _run() -> str:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) != "PeopleScreen"


# ---------------------------------------------------------------------------
# 13. test_empty_list_shows_placeholder
# ---------------------------------------------------------------------------


def test_empty_list_shows_placeholder() -> None:
    """0 people renders a (no people) placeholder."""

    async def _run() -> bool:
        app = _make_app(people=[], detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            found = len(list(app.screen.query("#no-people-label"))) > 0
            return found

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# 14. test_apply_people_updates_state
# ---------------------------------------------------------------------------


def test_apply_people_updates_state() -> None:
    """_apply_people updates people, search, selected, and status."""

    async def _run() -> tuple[int, str, int, str]:
        app = _make_app(people=_people(3), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            new_people = _people(2)
            screen._apply_people(new_people, "alice")
            await pilot.pause(0.05)
            return len(screen.people), screen.search, screen.selected, screen.status

    count, search, selected, status = asyncio.run(_run())
    assert count == 2
    assert search == "alice"
    assert selected == 0
    assert "2 person" in status


# ---------------------------------------------------------------------------
# 15. test_fetch_list_worker_no_token_sets_auth_failed
# ---------------------------------------------------------------------------


def test_fetch_list_worker_no_token_sets_auth_failed() -> None:
    """Worker with no token sets status to 'auth failed'."""

    async def _run() -> str:
        app = _make_app(people=_people(1), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with patch.object(screen, "_get_token_sync", return_value=""):
                screen._fetch_list(search="")
                await app.workers.wait_for_complete()
                await pilot.pause()
            return screen.status

    status = asyncio.run(_run())
    assert status == "auth failed"


# ---------------------------------------------------------------------------
# Bonus: detail pane bottom layout
# ---------------------------------------------------------------------------


def test_screen_detail_pane_bottom_shows_pane() -> None:
    """detail_pane='bottom' mounts a DetailPane widget."""

    async def _run() -> int:
        app = _make_app(detail_pane="bottom")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(DetailPane)))

    assert asyncio.run(_run()) >= 1


# ---------------------------------------------------------------------------
# Bonus: search cancelled leaves people unchanged
# ---------------------------------------------------------------------------


def test_screen_search_cancelled() -> None:
    """Pressing Escape in search modal leaves people unchanged."""

    async def _run() -> tuple[str, int]:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            original_search = screen.search
            original_count = len(screen.people)
            await pilot.press("/")
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return screen.search, len(screen.people), original_search, original_count

    search, count, original_search, original_count = asyncio.run(_run())
    assert search == original_search
    assert count == original_count
