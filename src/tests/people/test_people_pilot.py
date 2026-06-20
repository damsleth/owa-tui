"""Pilot tests for PeopleScreen — all 15 plan cases covered.

Tests follow the project pattern: async helpers wrapped in asyncio.run()
so plain pytest (no pytest-asyncio) can execute them.

All owa-tools / auth calls are mocked — no live Microsoft calls.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

from owa_tui.people.settings import PeopleSettings
from owa_tui.screens.people import DetailPane, DetailScreen, PeopleScreen, SearchModal

_FIXTURE_DIR = str(Path(__file__).resolve().parents[2].parent / "e2e" / "fixtures")

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


# ---------------------------------------------------------------------------
# Hardening: _fetch_list worker body (blocks 452-481)
# ---------------------------------------------------------------------------


def test_fetch_list_worker_fixture_success() -> None:
    """Worker with token + fixture loads, normalizes, and applies people."""

    async def _run() -> tuple[int, str]:
        app = _make_app(people=_people(1), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            os.environ["OWA_TUI_FIXTURES"] = _FIXTURE_DIR
            try:
                with patch.object(screen, "_get_token_sync", return_value="tok"):
                    screen._fetch_list(search="alice")
                    await app.workers.wait_for_complete()
                    await pilot.pause()
            finally:
                os.environ.pop("OWA_TUI_FIXTURES", None)
            return len(screen.people), screen.status

    count, status = asyncio.run(_run())
    assert count >= 1
    assert "person" in status


def test_fetch_list_worker_no_data_sets_fetch_failed() -> None:
    """Worker with token but api_get returning None sets 'fetch failed'."""

    async def _run() -> str:
        app = _make_app(people=_people(1), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with (
                patch.object(screen, "_get_token_sync", return_value="tok"),
                patch("owa_people.api.api_get", return_value=None),
            ):
                screen._fetch_list(search="")
                await app.workers.wait_for_complete()
                await pilot.pause()
            return screen.status

    assert "fetch failed" in asyncio.run(_run())


def test_fetch_list_worker_exception_sets_error() -> None:
    """An exception in the worker body is caught and surfaced as 'error:'."""

    async def _run() -> str:
        app = _make_app(people=_people(1), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with (
                patch.object(screen, "_get_token_sync", return_value="tok"),
                patch("owa_people.api.api_get", side_effect=RuntimeError("boom")),
            ):
                screen._fetch_list(search="")
                await app.workers.wait_for_complete()
                await pilot.pause()
            return screen.status

    assert "error: boom" in asyncio.run(_run())


# ---------------------------------------------------------------------------
# Hardening: _fetch_detail worker body (blocks 502-532)
# ---------------------------------------------------------------------------


def test_fetch_detail_worker_success_caches_and_shows() -> None:
    """Detail worker fetches via api_get, caches, and pushes DetailScreen."""
    people = _people(1)
    pid = people[0]["id"]
    raw = {"id": pid, "displayName": "Person 0", "jobTitle": "Lead"}

    async def _run() -> tuple[bool, type]:
        app = _make_app(people=people, detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with (
                patch.object(screen, "_get_token_sync", return_value="tok"),
                patch("owa_people.api.api_get", return_value=raw),
            ):
                screen._fetch_detail(pid)
                await app.workers.wait_for_complete()
                await pilot.pause(0.1)
            return pid in screen._detail_cache, type(app.screen)

    cached, top = asyncio.run(_run())
    assert cached
    assert top is DetailScreen


def test_fetch_detail_worker_no_token_fails() -> None:
    """Detail worker with no token calls _on_detail_failed."""
    people = _people(1)
    pid = people[0]["id"]

    async def _run() -> tuple[str, str]:
        app = _make_app(people=people, detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with patch.object(screen, "_get_token_sync", return_value=""):
                screen._fetch_detail(pid)
                await app.workers.wait_for_complete()
                await pilot.pause()
            return screen.status, screen.mode

    status, mode = asyncio.run(_run())
    assert "failed" in status
    assert mode == "list"


def test_fetch_detail_worker_exception_sets_status() -> None:
    """An exception in the detail worker is caught and surfaced."""
    people = _people(1)
    pid = people[0]["id"]

    async def _run() -> tuple[str, str]:
        app = _make_app(people=people, detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with (
                patch.object(screen, "_get_token_sync", return_value="tok"),
                patch("owa_people.api.api_get", side_effect=RuntimeError("nope")),
            ):
                screen._fetch_detail(pid)
                await app.workers.wait_for_complete()
                await pilot.pause()
            return screen.status, screen.mode

    status, mode = asyncio.run(_run())
    assert "failed to load person" in status
    assert mode == "list"


# ---------------------------------------------------------------------------
# Hardening: navigation + pane actions (blocks 565-619)
# ---------------------------------------------------------------------------


def test_screen_k_moves_selection_up() -> None:
    """Pressing k after j x2 moves selection back up to index 1."""

    async def _run() -> int:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j", "j", "k")
            await pilot.pause(0.05)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            return screen.selected

    assert asyncio.run(_run()) == 1


def test_close_detail_with_pane_returns_to_list() -> None:
    """action_close_detail with a visible pane focuses the list and sets mode=list."""

    async def _run() -> str:
        app = _make_app(detail_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen.mode = "detail"
            screen.action_close_detail()
            await pilot.pause(0.05)
            return screen.mode

    assert asyncio.run(_run()) == "list"


def test_focus_pane_toggles_focus() -> None:
    """action_focus_pane moves focus onto the detail pane, then back to the list."""

    async def _run() -> bool:
        app = _make_app(detail_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            pane = screen.query_one("#detail-pane", DetailPane)
            screen.action_focus_pane()
            await pilot.pause(0.05)
            on_pane = screen.focused is pane
            screen.action_focus_pane()
            await pilot.pause(0.05)
            off_pane = screen.focused is not pane
            return on_pane and off_pane

    assert asyncio.run(_run())


def test_focus_pane_noop_when_pane_off() -> None:
    """action_focus_pane is a no-op when detail_pane is off."""

    async def _run() -> None:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen.action_focus_pane()  # must not raise
            await pilot.pause(0.05)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Hardening: settings overlay handler (blocks 652-682)
# ---------------------------------------------------------------------------


def test_handle_overlay_help_sets_status() -> None:
    """Overlay 'help' result sets a help status line."""

    async def _run() -> str:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._handle_overlay("help")
            await pilot.pause(0.05)
            return screen.status

    assert "search" in asyncio.run(_run())


def test_handle_overlay_resume_is_noop() -> None:
    """Overlay 'resume' result leaves settings unchanged."""

    async def _run() -> str:
        app = _make_app(detail_pane="off", sort_by="name_asc")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._handle_overlay("resume")
            await pilot.pause(0.05)
            return screen.settings.sort_by

    assert asyncio.run(_run()) == "name_asc"


def test_handle_overlay_cycle_applies_and_persists() -> None:
    """Overlay 'cycle:sort_by' changes the sort setting via _apply_settings."""

    async def _run() -> str:
        app = _make_app(detail_pane="off", sort_by="name_asc")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            # _persist_settings hits owa_people.config; swallow whatever it does.
            screen._handle_overlay("cycle:sort_by")
            await pilot.pause(0.05)
            return screen.settings.sort_by

    assert asyncio.run(_run()) != "name_asc"


def test_handle_overlay_quit_exits_app() -> None:
    """Overlay 'quit' result exits the app."""

    async def _run() -> bool:
        app = _make_app(detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._handle_overlay("quit")
            await pilot.pause(0.1)
            return app._exit

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# Hardening: detail display paths (blocks 502-549) + token mint
# ---------------------------------------------------------------------------


def test_open_detail_action_cached_shows_screen() -> None:
    """action_open_detail with a cached person shows the DetailScreen directly."""
    people = _people(1)
    pid = people[0]["id"]

    async def _run() -> type:
        app = _make_app(people=people, detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._detail_cache[pid] = {**people[0], "jobTitle": "Lead"}
            screen.action_open_detail()
            await pilot.pause(0.1)
            return type(app.screen)

    assert asyncio.run(_run()) is DetailScreen


def test_open_detail_action_no_person_is_noop() -> None:
    """action_open_detail with an empty list does nothing and does not raise."""

    async def _run() -> type:
        app = _make_app(people=[], detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen.action_open_detail()
            await pilot.pause(0.05)
            return type(app.screen)

    assert asyncio.run(_run()) is PeopleScreen


def test_fetch_detail_worker_cached_shows_directly() -> None:
    """Detail worker short-circuits to _show_cached_detail when already cached."""
    people = _people(1)
    pid = people[0]["id"]

    async def _run() -> type:
        app = _make_app(people=people, detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._detail_cache[pid] = {**people[0]}
            screen._fetch_detail(pid)
            await app.workers.wait_for_complete()
            await pilot.pause(0.1)
            return type(app.screen)

    assert asyncio.run(_run()) is DetailScreen


def test_show_cached_detail_in_pane() -> None:
    """_show_cached_detail with a visible pane renders into it and sets mode=detail."""
    people = _people(1)
    pid = people[0]["id"]

    async def _run() -> str:
        app = _make_app(people=people, detail_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._detail_cache[pid] = {**people[0], "jobTitle": "Lead"}
            screen._show_cached_detail(pid)
            await pilot.pause(0.05)
            return screen.mode

    assert asyncio.run(_run()) == "detail"


def test_show_cached_detail_missing_fails() -> None:
    """_show_cached_detail for an unknown id falls back to _on_detail_failed."""

    async def _run() -> str:
        app = _make_app(people=_people(1), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            screen._show_cached_detail("does-not-exist")
            await pilot.pause(0.05)
            return screen.status

    assert "failed" in asyncio.run(_run())


def test_get_token_sync_delegates_to_adapter() -> None:
    """_get_token_sync returns whatever access_token_for yields."""

    async def _run() -> str:
        app = _make_app(people=_people(1), detail_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: PeopleScreen = app.screen  # type: ignore[assignment]
            with patch("owa_tui.adapter.access_token_for", return_value="minted"):
                return screen._get_token_sync()

    assert asyncio.run(_run()) == "minted"
