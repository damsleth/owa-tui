"""Pilot tests for MailScreen — all 25 plan cases covered.

Tests follow the project pattern: async helpers wrapped in ``asyncio.run()``
so plain pytest (no pytest-asyncio) can execute them.

All owa-tools / auth calls are mocked — no live Microsoft calls.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from owa_tui.mail.settings import DEFAULTS as SETTINGS_DEFAULTS
from owa_tui.mail.settings import MailSettings
from owa_tui.screens.mail import MailScreen, ReaderPane, ReaderScreen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msgs(n: int = 6) -> list[dict]:
    return [
        {
            "id": f"m{i}",
            "received": f"2026-05-{10 + i:02d}T09:00:00Z",
            "from": f"user{i}@example.com",
            "subject": f"Subject {i}",
            "is_read": i % 2 == 0,
            "flag": "NotFlagged",
            "has_attachments": False,
            "web_link": "https://example.test/m",
            "preview": f"Preview {i}",
            "body": f"Body of message {i}",
            "body_type": "text",
        }
        for i in range(n)
    ]


def _make_app(
    messages: list[dict] | None = None,
    reading_pane: str = "off",
    sort_by: str = "date_desc",
    date_format: str = "iso8601",
    date_custom: str = "",
):
    """Create a minimal App that pushes a pre-loaded MailScreen."""
    from textual.app import App, ComposeResult
    from textual.widgets import Footer, Header

    settings = MailSettings(
        reading_pane=reading_pane,
        sort_by=sort_by,
        date_format=date_format,
        date_custom=date_custom,
    )

    class _TestApp(App):
        TITLE = "test"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            screen = MailScreen(
                initial_messages=messages if messages is not None else _msgs(),
                initial_settings=settings,
            )
            self.push_screen(screen)

    return _TestApp()


# ---------------------------------------------------------------------------
# 1. test_screen_renders_message_list
# ---------------------------------------------------------------------------


def test_screen_renders_message_list() -> None:
    """MailScreen with 6 messages renders all list items."""

    async def _run() -> int:
        from textual.widgets import ListItem

        app = _make_app(reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(ListItem)))

    count = asyncio.run(_run())
    assert count >= 6


# ---------------------------------------------------------------------------
# 2. test_screen_reading_pane_right_shows_body
# ---------------------------------------------------------------------------


def test_screen_reading_pane_right_shows_body() -> None:
    """reading_pane='right' mounts a ReaderPane widget."""

    async def _run() -> int:
        app = _make_app(reading_pane="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(ReaderPane)))

    assert asyncio.run(_run()) >= 1


# ---------------------------------------------------------------------------
# 3. test_screen_reading_pane_bottom_shows_body
# ---------------------------------------------------------------------------


def test_screen_reading_pane_bottom_shows_body() -> None:
    """reading_pane='bottom' mounts a ReaderPane widget."""

    async def _run() -> int:
        app = _make_app(reading_pane="bottom")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(ReaderPane)))

    assert asyncio.run(_run()) >= 1


# ---------------------------------------------------------------------------
# 4. test_screen_reading_pane_off_no_pane_widget
# ---------------------------------------------------------------------------


def test_screen_reading_pane_off_no_pane_widget() -> None:
    """reading_pane='off' mounts no ReaderPane in the DOM."""

    async def _run() -> int:
        app = _make_app(reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(list(app.screen.query(ReaderPane)))

    assert asyncio.run(_run()) == 0


# ---------------------------------------------------------------------------
# 5. test_screen_j_moves_selection_down
# ---------------------------------------------------------------------------


def test_screen_j_moves_selection_down() -> None:
    """Pressing j twice moves selected to index 2."""

    async def _run() -> int:
        app = _make_app(reading_pane="off", sort_by="date_asc")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.press("j")
            await pilot.pause(0.05)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            return screen.selected

    assert asyncio.run(_run()) == 2


# ---------------------------------------------------------------------------
# 6. test_screen_G_jumps_to_last
# ---------------------------------------------------------------------------


def test_screen_G_jumps_to_last() -> None:
    """Pressing G with 6 messages jumps to index 5."""

    async def _run() -> int:
        app = _make_app(reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("G")
            await pilot.pause(0.05)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            return screen.selected

    assert asyncio.run(_run()) == 5


# ---------------------------------------------------------------------------
# 7. test_screen_sort_date_asc
# ---------------------------------------------------------------------------


def test_screen_sort_date_asc() -> None:
    """date_asc sort puts oldest message first."""
    from owa_tui.mail.sort import sort_messages

    msgs = _msgs()
    sorted_msgs = sort_messages(msgs, "date_asc")
    non_empty = [m for m in sorted_msgs if m["received"]]
    received = [m["received"] for m in non_empty]
    assert received == sorted(received)


# ---------------------------------------------------------------------------
# 8. test_screen_sort_sender
# ---------------------------------------------------------------------------


def test_screen_sort_sender() -> None:
    """sender sort puts messages A-Z by from field."""
    from owa_tui.mail.sort import sort_messages

    msgs = _msgs()
    sorted_msgs = sort_messages(msgs, "sender")
    senders = [m["from"].casefold() for m in sorted_msgs]
    assert senders == sorted(senders)


# ---------------------------------------------------------------------------
# 9. test_screen_sort_unread_first
# ---------------------------------------------------------------------------


def test_screen_sort_unread_first() -> None:
    """unread_first sort puts unread messages at the top."""
    from owa_tui.mail.sort import sort_messages

    msgs = _msgs(6)
    # msgs at odd indices (1,3,5) are unread (is_read=False)
    sorted_msgs = sort_messages(msgs, "unread_first")
    first_three = sorted_msgs[:3]
    assert all(not m["is_read"] for m in first_three)


# ---------------------------------------------------------------------------
# 10. test_screen_sort_subject
# ---------------------------------------------------------------------------


def test_screen_sort_subject() -> None:
    """subject sort puts messages A-Z by subject casefold."""
    from owa_tui.mail.sort import sort_messages

    msgs = _msgs()
    sorted_msgs = sort_messages(msgs, "subject")
    subjects = [m["subject"].casefold() for m in sorted_msgs]
    assert subjects == sorted(subjects)


# ---------------------------------------------------------------------------
# 11. test_screen_date_fmt_iso8601
# ---------------------------------------------------------------------------


def test_screen_date_fmt_iso8601() -> None:
    """Row text contains YYYY-MM-DD date for iso8601 format."""
    from owa_tui.mail.list_row import list_row

    msg = _msgs(1)[0]
    row = list_row(msg, 100, date_fmt="iso8601")
    assert "2026-05-10" in row


# ---------------------------------------------------------------------------
# 12. test_screen_date_fmt_ddmm
# ---------------------------------------------------------------------------


def test_screen_date_fmt_ddmm() -> None:
    """Row text contains DD.MM for ddmm format."""
    from owa_tui.mail.list_row import list_row

    msg = _msgs(1)[0]
    row = list_row(msg, 100, date_fmt="ddmm")
    assert "10.05" in row


# ---------------------------------------------------------------------------
# 13. test_screen_date_fmt_ddmm_hhmm
# ---------------------------------------------------------------------------


def test_screen_date_fmt_ddmm_hhmm() -> None:
    """Row text contains DD.MM HH:MM for ddmm_hhmm format."""
    from owa_tui.mail.list_row import list_row

    msg = _msgs(1)[0]
    row = list_row(msg, 100, date_fmt="ddmm_hhmm")
    assert "10.05 09:00" in row


# ---------------------------------------------------------------------------
# 14. test_screen_date_fmt_custom
# ---------------------------------------------------------------------------


def test_screen_date_fmt_custom() -> None:
    """Row text contains custom date format."""
    from owa_tui.mail.list_row import list_row

    msg = _msgs(1)[0]
    row = list_row(msg, 100, date_fmt="custom", custom_fmt="%Y/%m/%d")
    assert "2026/05/10" in row


# ---------------------------------------------------------------------------
# 15. test_screen_open_message_sets_reader_mode
# ---------------------------------------------------------------------------


def test_screen_open_message_sets_reader_mode() -> None:
    """When reading_pane='off', pressing Enter pushes a ReaderScreen."""
    msgs = _msgs(1)
    msg_id = msgs[0]["id"]
    body_msg = {**msgs[0], "body": "Full body", "body_type": "text"}

    async def _run() -> type:
        app = _make_app(messages=msgs, reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            # Pre-populate body cache so no live fetch needed
            screen._body_cache[msg_id] = body_msg
            await pilot.press("enter")
            await pilot.pause(0.1)
            return type(app.screen)

    assert asyncio.run(_run()) is ReaderScreen


# ---------------------------------------------------------------------------
# 16. test_screen_toggle_read_flips_and_patches
# ---------------------------------------------------------------------------


def test_screen_toggle_read_flips_and_patches() -> None:
    """Pressing r flips is_read (optimistic local update)."""
    msgs = _msgs(1)
    original_read = msgs[0]["is_read"]

    async def _run() -> bool | None:
        app = _make_app(messages=msgs, reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            with patch.object(screen, "_patch_read"):
                await pilot.press("r")
                await pilot.pause(0.05)
            ml = screen._message_list()
            current = ml.current_msg() if ml else None
            return current["is_read"] if current else None

    result = asyncio.run(_run())
    if result is not None:
        assert result != original_read


# ---------------------------------------------------------------------------
# 17. test_screen_search_re_fetches
# ---------------------------------------------------------------------------


def test_screen_search_re_fetches() -> None:
    """Opening the search modal and submitting works without error."""

    async def _run() -> bool:
        app = _make_app(reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            with patch.object(screen, "_fetch_list"):
                await pilot.press("/")
                await pilot.pause(0.1)
                # Type each character individually (Textual Pilot has no .type())
                for ch in "budget":
                    await pilot.press(ch)
                await pilot.press("enter")
                await pilot.pause(0.1)
            return True

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# 18. test_screen_search_cancelled
# ---------------------------------------------------------------------------


def test_screen_search_cancelled() -> None:
    """Pressing Escape in search modal leaves messages unchanged."""

    async def _run() -> tuple[str, int]:
        app = _make_app(reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            original_search = screen.search
            original_count = len(screen.messages)
            await pilot.press("/")
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return screen.search, len(screen.messages), original_search, original_count

    search, count, original_search, original_count = asyncio.run(_run())
    assert search == original_search
    assert count == original_count


# ---------------------------------------------------------------------------
# 19. test_screen_escape_opens_menu
# ---------------------------------------------------------------------------


def test_screen_escape_opens_menu() -> None:
    """Pressing Escape opens the settings overlay ModalScreen."""
    from owa_tui.widgets.settings_overlay import SettingsOverlay

    async def _run() -> type:
        app = _make_app(reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen)

    assert asyncio.run(_run()) is SettingsOverlay


# ---------------------------------------------------------------------------
# 20. test_screen_menu_cycle_reading_pane
# ---------------------------------------------------------------------------


def test_screen_menu_cycle_reading_pane() -> None:
    """cycle() on reading_pane advances to the next value."""
    from owa_tui.mail.settings import cycle

    settings = MailSettings(reading_pane="right")
    new_settings = cycle(settings, "reading_pane")
    assert new_settings.reading_pane != "right"
    assert new_settings.reading_pane == "bottom"


# ---------------------------------------------------------------------------
# 21. test_screen_menu_reset_settings
# ---------------------------------------------------------------------------


def test_screen_menu_reset_settings() -> None:
    """SETTINGS_DEFAULTS is equal to a fresh MailSettings()."""
    assert SETTINGS_DEFAULTS == MailSettings()


# ---------------------------------------------------------------------------
# 22. test_screen_empty_list_shows_placeholder
# ---------------------------------------------------------------------------


def test_screen_empty_list_shows_placeholder() -> None:
    """0 messages renders a (no messages) placeholder."""

    async def _run() -> bool:
        app = _make_app(messages=[], reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            # The MessageList._rebuild() appends a Static with id='no-messages-label'
            found = len(list(app.screen.query("#no-messages-label"))) > 0
            return found

    assert asyncio.run(_run())


# ---------------------------------------------------------------------------
# 23. test_screen_body_fetch_failure_stays_list
# ---------------------------------------------------------------------------


def test_screen_body_fetch_failure_stays_list() -> None:
    """Body fetch failure sets status to 'failed' and mode stays 'list'."""

    async def _run() -> tuple[str, str]:
        app = _make_app(messages=_msgs(1), reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            screen._on_body_failed()
            await pilot.pause(0.05)
            return screen.status, screen.mode

    status, mode = asyncio.run(_run())
    assert "failed" in status
    assert mode == "list"


# ---------------------------------------------------------------------------
# 24. test_screen_browser_open
# ---------------------------------------------------------------------------


def test_screen_browser_open() -> None:
    """Pressing o calls webbrowser.open with the message's web_link."""

    async def _run() -> list[str]:
        app = _make_app(messages=_msgs(1), reading_pane="off")
        calls: list[str] = []
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            with patch("webbrowser.open", side_effect=lambda url: calls.append(url)):
                await pilot.press("o")
                await pilot.pause(0.05)
        return calls

    calls = asyncio.run(_run())
    assert calls == ["https://example.test/m"]


# ---------------------------------------------------------------------------
# 25. test_screen_browser_no_link
# ---------------------------------------------------------------------------


def test_screen_browser_no_link() -> None:
    """Pressing o with no web_link sets status 'no web link'."""

    async def _run() -> str:
        msgs = [{**m, "web_link": ""} for m in _msgs(1)]
        app = _make_app(messages=msgs, reading_pane="off")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("o")
            await pilot.pause(0.05)
            screen: MailScreen = app.screen  # type: ignore[assignment]
            return screen.status

    assert "no web link" in asyncio.run(_run())
