"""Folder panel (show/hide, select) and scroll-to-load pagination."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.mail.settings import MailSettings, cycle, from_config, to_config_dict
from owa_tui.screens.mail import FolderList, MailScreen


def _msgs(n: int) -> list[dict]:
    return [{"id": f"m{i}", "received": f"2026-05-{10 + i:02d}T09:00:00Z",
             "from": f"u{i}@x.com", "subject": f"S{i}", "is_read": True} for i in range(n)]


def _make_app(messages, show_folders=False):
    settings = MailSettings(reading_pane="off", show_folders=show_folders)

    class _TestApp(App):
        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(MailScreen(initial_messages=messages, initial_settings=settings))

    return _TestApp()


# ── settings ──────────────────────────────────────────────────────────────

def test_show_folders_settings_roundtrip() -> None:
    assert cycle(MailSettings(), "show_folders").show_folders is True
    assert from_config({"tui_show_folders": "true"}).show_folders is True
    assert from_config({"tui_show_folders": "false"}).show_folders is False
    assert to_config_dict(MailSettings(show_folders=True))["tui_show_folders"] == "true"


# ── FolderList widget ───────────────────────────────────────────────────────

def test_folder_list_populates_and_selects() -> None:
    async def _run():
        app = _make_app(_msgs(3), show_folders=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            screen._apply_folders([{"id": "2", "name": "Sent"}, {"id": "1", "name": "Inbox"}])
            await pilot.pause(0.05)
            fl = screen.query_one("#folder-list", FolderList)
            n = len(fl._folders)
            # Selecting a folder routes through the handler and sets the scope.
            screen._messages_preloaded = True  # don't fire a live fetch
            screen.on_folder_list_folder_selected(
                FolderList.FolderSelected({"id": "2", "name": "Sent"})
            )
            await pilot.pause(0.05)
            return n, screen._folder_id, screen.folder

    n, folder_id, folder_name = asyncio.run(_run())
    assert n == 2
    assert folder_id == "2"
    assert folder_name == "Sent"


def test_fetch_folders_worker_loads_from_fixture(tmp_path, monkeypatch) -> None:
    """The live ``_fetch_folders`` worker: token mint → fixture load →
    normalize → ``_apply_folders``. Driven end-to-end via OWA_TUI_FIXTURES
    (e2e covers the keypress path; this covers the worker body in Python)."""
    (tmp_path / "mail_folders.json").write_text(
        json.dumps(
            {
                "value": [
                    {"Id": "Inbox", "DisplayName": "Inbox", "UnreadItemCount": 2},
                    {"Id": "Archive", "DisplayName": "Archive", "UnreadItemCount": 0},
                ]
            }
        )
    )
    monkeypatch.setenv("OWA_TUI_FIXTURES", str(tmp_path))

    async def _run():
        app = _make_app(_msgs(1), show_folders=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            screen._fetch_folders()  # drive the live worker (fixture-backed)
            await app.workers.wait_for_complete()  # let the thread worker finish
            await pilot.pause(0.05)
            fl = screen.query_one("#folder-list", FolderList)
            return [f["name"] for f in fl._folders], [f["unread"] for f in fl._folders]

    names, unread = asyncio.run(_run())
    assert names == ["Inbox", "Archive"]
    assert unread == [2, 0]


# ── pagination ──────────────────────────────────────────────────────────────

def test_append_messages_dedupes_and_keeps_cursor() -> None:
    async def _run():
        app = _make_app(_msgs(50))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            ml = screen._message_list()
            ml.index = 49
            # Next page overlaps m49 (dup) and adds m50, m51.
            page2 = [{"id": "m49"}, {"id": "m50"}, {"id": "m51"}]
            screen._append_messages(page2)
            await pilot.pause(0.05)
            return len(screen.messages), ml.index

    total, idx = asyncio.run(_run())
    assert total == 52  # 50 + 2 fresh, m49 de-duped
    assert idx == 49  # cursor stayed put


def test_short_page_stops_pagination() -> None:
    async def _run():
        app = _make_app(_msgs(50))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            screen._append_messages([{"id": "m50"}])  # < PAGE_SIZE
            return screen._has_more

    assert asyncio.run(_run()) is False


def test_maybe_load_more_fires_at_last_row() -> None:
    async def _run():
        app = _make_app(_msgs(50))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            screen._messages_preloaded = False  # simulate a live (paginating) screen
            screen._has_more = True
            screen._fetch_list = MagicMock()  # type: ignore[method-assign]
            ml = screen._message_list()
            ml.index = 49  # last row
            screen._maybe_load_more(ml)
            mid_called = screen._fetch_list.called
            # Not at last row → no fetch
            screen._fetch_list.reset_mock()
            screen._loading_more = False
            ml.index = 10
            screen._maybe_load_more(ml)
            return mid_called, screen._fetch_list.called

    fired_at_last, fired_mid = asyncio.run(_run())
    assert fired_at_last is True
    assert fired_mid is False


# ── folder panel toggle ─────────────────────────────────────────────────────

def test_toggle_folders_mounts_and_removes_pane() -> None:
    async def _run():
        app = _make_app(_msgs(3), show_folders=False)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            before = len(list(screen.query("#folder-list")))
            screen.action_toggle_folders()
            await pilot.pause(0.05)
            after_on = len(list(screen.query("#folder-list")))
            screen.action_toggle_folders()
            await pilot.pause(0.05)
            after_off = len(list(screen.query("#folder-list")))
            return before, after_on, after_off

    before, on, off = asyncio.run(_run())
    assert (before, on, off) == (0, 1, 0)


def test_show_folders_renders_pane_on_compose() -> None:
    async def _run():
        app = _make_app(_msgs(3), show_folders=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            return len(list(screen.query("#folder-list")))

    assert asyncio.run(_run()) == 1
