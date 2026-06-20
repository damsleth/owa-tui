"""Unit and Pilot tests for TeamsScreen + TeamsThreadScreen.

Coverage targets:
- Pure helpers: _chat_display_name, _row_text, _detail_text, _render_message_block
- TeamsScreen.fetch_items: fixture path, search filter, no-fixture (mocked live)
- TeamsScreen pilot: list renders, j+l opens thread, h closes, menu, refresh, search
- TeamsThreadScreen.fetch_messages: per-chat fixture, fallback fixture, mocked live
- render_row / render_detail / render_message via screen methods
- on_item_activated: pushes TeamsThreadScreen
- menu_config, sort_items, help_text
- Registration in SCREEN_REGISTRY
- Mocked live path: access_token_for + httpx calls
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.teams import (
    TeamsScreen,
    TeamsThreadScreen,
    _chat_display_name,
    _detail_text,
    _render_message_block,
    _row_text,
)

# ---------------------------------------------------------------------------
# Fixtures directory (e2e/fixtures)
# ---------------------------------------------------------------------------

FIXTURE_DIR = str(
    pathlib.Path(__file__).parent.parent.parent.parent / "e2e" / "fixtures"
)


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------


def _chat(
    *,
    id: str = "19:test@thread.v2",
    topic: str | None = "Test Chat",
    chat_type: str = "group",
    members: list[str] | None = None,
    last_updated: str = "2026-06-19T10:00:00Z",
) -> dict:
    member_names = members or ["Alice Strand", "Carl Damsleth"]
    return {
        "id": id,
        "topic": topic,
        "chatType": chat_type,
        "createdDateTime": "2026-06-01T08:00:00Z",
        "lastUpdatedDateTime": last_updated,
        "webUrl": f"https://teams.microsoft.com/l/chat/{id}",
        "_memberNames": member_names,
    }


def _chats(n: int = 3) -> list[dict]:
    types = ["group", "meeting", "oneOnOne"]
    topics = ["Engineering Standup", "Q2 Review", None]
    members_list = [
        ["Alice Strand", "Bob Nguyen", "Carl Damsleth"],
        ["Alice Strand", "Carl Damsleth"],
        ["Alice Strand", "Carl Damsleth"],
    ]
    results = []
    for i in range(n):
        results.append(
            _chat(
                id=f"19:chat-{i:03d}@thread.v2",
                topic=topics[i % len(topics)],
                chat_type=types[i % len(types)],
                members=members_list[i % len(members_list)],
                last_updated=f"2026-06-{15 + i:02d}T10:00:00Z",
            )
        )
    return results


def _message(
    *,
    msg_id: str = "msg-001",
    sender_name: str = "Alice Strand",
    sender_id: str = "user-001",
    content: str = "Hello world",
    content_type: str = "text",
    created: str = "2026-06-19T09:00:00Z",
    deleted: str | None = None,
) -> dict:
    return {
        "id": msg_id,
        "createdDateTime": created,
        "deletedDateTime": deleted,
        "from": {"user": {"id": sender_id, "displayName": sender_name}},
        "body": {"contentType": content_type, "content": content},
    }


def _messages(n: int = 3) -> list[dict]:
    senders = [("Alice Strand", "user-001"), ("Bob Nguyen", "user-002"), ("Carl Damsleth", "user-003")]
    return [
        _message(
            msg_id=f"msg-{i:03d}",
            sender_name=senders[i % len(senders)][0],
            sender_id=senders[i % len(senders)][1],
            content=f"Message number {i}",
            created=f"2026-06-19T09:{i:02d}:00Z",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# App factories
# ---------------------------------------------------------------------------


def _make_teams_app(**screen_kw: Any) -> App:
    # TeamsScreen hard-codes detail_pane_mode="right" — strip it from kwargs
    # so tests that pass detail_pane_mode don't trigger "multiple values" errors.
    screen_kw.pop("detail_pane_mode", None)

    class _TestApp(App):
        TITLE = "test-teams"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(TeamsScreen(**screen_kw))

    return _TestApp()


def _make_thread_app(**screen_kw: Any) -> App:
    class _TestApp(App):
        TITLE = "test-thread"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(
                TeamsThreadScreen(
                    {},
                    chat_id=screen_kw.pop("chat_id", "19:test@thread.v2"),
                    chat_name=screen_kw.pop("chat_name", "Test Chat"),
                    **screen_kw,
                )
            )

    return _TestApp()


# ===========================================================================
# Pure helper tests — no Textual app needed
# ===========================================================================


class TestChatDisplayName:
    def test_topic_takes_priority(self) -> None:
        chat = _chat(topic="Project Alpha", members=["Alice", "Bob"])
        assert _chat_display_name(chat) == "Project Alpha"

    def test_no_topic_falls_back_to_members(self) -> None:
        chat = _chat(topic=None, members=["Alice Strand", "Carl Damsleth"])
        name = _chat_display_name(chat)
        assert "Alice Strand" in name
        assert "Carl Damsleth" in name

    def test_no_topic_no_members_falls_back_to_id(self) -> None:
        chat = {"id": "19:abc123@thread.v2", "topic": None, "_memberNames": []}
        name = _chat_display_name(chat)
        assert "19:abc123" in name

    def test_more_than_three_members_truncated_with_ellipsis(self) -> None:
        chat = _chat(topic=None, members=["A", "B", "C", "D", "E"])
        name = _chat_display_name(chat)
        assert "…" in name

    def test_exactly_three_members_no_ellipsis(self) -> None:
        chat = _chat(topic=None, members=["A", "B", "C"])
        name = _chat_display_name(chat)
        assert "…" not in name


class TestRowText:
    def test_group_chat_shows_grp_tag(self) -> None:
        chat = _chat(chat_type="group", topic="Team Chat")
        row = _row_text(chat, width=80)
        assert "[grp]" in row
        assert "Team Chat" in row

    def test_one_on_one_shows_1_1_tag(self) -> None:
        chat = _chat(chat_type="oneOnOne", topic=None, members=["Alice", "Carl"])
        row = _row_text(chat, width=80)
        assert "[1:1]" in row

    def test_meeting_shows_mtg_tag(self) -> None:
        chat = _chat(chat_type="meeting", topic="Q2 Review")
        row = _row_text(chat, width=80)
        assert "[mtg]" in row

    def test_unknown_type_shows_question_mark(self) -> None:
        chat = _chat(chat_type="unknown_type", topic="Weird Chat")
        row = _row_text(chat, width=80)
        assert "[?]" in row

    def test_long_name_truncated(self) -> None:
        chat = _chat(topic="X" * 200, chat_type="group")
        row = _row_text(chat, width=60)
        assert len(row) <= 65  # slight tolerance
        assert "…" in row

    def test_short_width_does_not_crash(self) -> None:
        chat = _chat(topic="A", chat_type="group")
        row = _row_text(chat, width=20)
        assert isinstance(row, str)


class TestDetailText:
    def test_full_chat_shows_name(self) -> None:
        chat = _chat(topic="Engineering", chat_type="group")
        detail = _detail_text(chat)
        assert "Engineering" in detail

    def test_detail_shows_chat_type(self) -> None:
        chat = _chat(topic="Mtg", chat_type="meeting")
        detail = _detail_text(chat)
        assert "meeting" in detail

    def test_detail_shows_members(self) -> None:
        chat = _chat(topic=None, members=["Alice Strand", "Carl Damsleth"])
        detail = _detail_text(chat)
        assert "Alice Strand" in detail
        assert "Carl Damsleth" in detail

    def test_detail_shows_web_url(self) -> None:
        chat = _chat(topic="Chat")
        detail = _detail_text(chat)
        assert "teams.microsoft.com" in detail

    def test_detail_shows_timestamps(self) -> None:
        chat = _chat(topic="Chat", last_updated="2026-06-19T10:00:00Z")
        detail = _detail_text(chat)
        assert "2026-06-19" in detail

    def test_empty_chat_does_not_crash(self) -> None:
        detail = _detail_text({})
        assert isinstance(detail, str)


class TestRenderMessageBlock:
    def test_text_message_shows_sender_and_content(self) -> None:
        msg = _message(sender_name="Alice Strand", content="Hello everyone")
        rendered = _render_message_block(msg)
        assert "Alice Strand" in rendered
        assert "Hello everyone" in rendered

    def test_html_message_strips_tags(self) -> None:
        msg = _message(
            content="<p>Hello <b>world</b></p>",
            content_type="html",
        )
        rendered = _render_message_block(msg)
        assert "<p>" not in rendered
        assert "<b>" not in rendered
        assert "Hello" in rendered
        assert "world" in rendered

    def test_deleted_message_shows_deleted(self) -> None:
        msg = _message(content="original", deleted="2026-06-19T10:00:00Z")
        rendered = _render_message_block(msg)
        assert "deleted" in rendered.lower()

    def test_timestamp_formatted_with_space(self) -> None:
        msg = _message(created="2026-06-19T09:30:00Z")
        rendered = _render_message_block(msg)
        assert "2026-06-19 09:30" in rendered

    def test_missing_sender_shows_question_mark(self) -> None:
        msg = {"id": "x", "body": {"contentType": "text", "content": "hi"}}
        rendered = _render_message_block(msg)
        assert "?" in rendered

    def test_separator_line_present(self) -> None:
        msg = _message()
        rendered = _render_message_block(msg)
        assert "─" in rendered


# ===========================================================================
# TeamsScreen pilot tests
# ===========================================================================


def test_list_renders_chats() -> None:
    async def _run() -> int:
        app = _make_teams_app(initial_items=_chats(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            return len(app.screen._items)

    assert asyncio.run(_run()) == 3


def test_j_moves_cursor() -> None:
    async def _run() -> int:
        app = _make_teams_app(initial_items=_chats(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.pause(0.05)
            return app.screen._selected_idx

    # ListView starts at index None; after j it advances to 0
    assert asyncio.run(_run()) >= 0


def test_j_then_l_opens_thread_screen() -> None:
    """Activating a chat item pushes TeamsThreadScreen onto the screen stack."""

    async def _run() -> str:
        app = _make_teams_app(initial_items=_chats(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.pause(0.05)
            # Intercept before any live fetch
            with patch.object(TeamsThreadScreen, "fetch_messages", return_value=[]):
                await pilot.press("l")
                await pilot.pause(0.2)
                return type(app.screen).__name__

    assert asyncio.run(_run()) == "TeamsThreadScreen"


def test_thread_screen_shows_chat_name_breadcrumb() -> None:
    """Thread screen breadcrumb shows the chat topic."""

    async def _run() -> str:
        app = _make_teams_app(initial_items=_chats(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.pause(0.05)
            with patch.object(TeamsThreadScreen, "fetch_messages", return_value=[]):
                await pilot.press("l")
                await pilot.pause(0.2)
                thread = app.screen
                return thread._breadcrumb

    result = asyncio.run(_run())
    assert isinstance(result, str)
    assert len(result) > 0


def test_h_pops_back_to_teams_screen() -> None:
    """h in TeamsThreadScreen pops back, showing TeamsScreen again."""

    async def _run() -> tuple[str, str]:
        app = _make_teams_app(initial_items=_chats(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("j")
            await pilot.pause(0.05)
            with patch.object(TeamsThreadScreen, "fetch_messages", return_value=[]):
                await pilot.press("l")
                await pilot.pause(0.2)
                screen_name = type(app.screen).__name__
                await pilot.press("h")
                await pilot.pause(0.15)
                after_pop = type(app.screen).__name__
                return screen_name, after_pop

    before, after = asyncio.run(_run())
    assert before == "TeamsThreadScreen"
    assert after == "TeamsScreen"


def test_escape_opens_menu() -> None:
    async def _run() -> str:
        app = _make_teams_app(initial_items=_chats(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "SettingsOverlay"


def test_q_quits() -> None:
    async def _run() -> str:
        app = _make_teams_app(initial_items=_chats(3), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) != "TeamsScreen"


def test_search_key_opens_modal() -> None:
    async def _run() -> str:
        app = _make_teams_app(initial_items=_chats(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("/")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) == "_SearchModal"


def test_refresh_triggers_fetch() -> None:
    chats = _chats(2)

    async def _run() -> int:
        with patch.object(TeamsScreen, "fetch_items", return_value=chats) as mock_fetch:
            app = _make_teams_app(detail_pane_mode="right")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                await pilot.press("r")
                await pilot.pause(0.3)
                return mock_fetch.call_count

    assert asyncio.run(_run()) >= 2


def test_fetch_worker_populates_list() -> None:
    chats = _chats(2)

    async def _run() -> int:
        with patch.object(TeamsScreen, "fetch_items", return_value=chats):
            app = _make_teams_app(detail_pane_mode="right")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return len(app.screen._items)

    assert asyncio.run(_run()) == 2


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        with patch.object(TeamsScreen, "fetch_items", side_effect=RuntimeError("net error")):
            app = _make_teams_app(detail_pane_mode="right")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return app.screen._status

    assert "error: net error" in asyncio.run(_run())


# ===========================================================================
# TeamsScreen.fetch_items unit tests
# ===========================================================================


def test_fetch_items_fixture_mode() -> None:
    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": FIXTURE_DIR}):
            screen = TeamsScreen(config={})
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 3
    topics = [c.get("topic") for c in items]
    assert "General Engineering" in topics
    assert "Q2 Review" in topics


def test_fetch_items_fixture_search_match() -> None:
    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": FIXTURE_DIR}):
            screen = TeamsScreen(config={})
            return await screen.fetch_items(search="Q2")

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["topic"] == "Q2 Review"


def test_fetch_items_fixture_search_no_match() -> None:
    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": FIXTURE_DIR}):
            screen = TeamsScreen(config={})
            return await screen.fetch_items(search="xyzzy-never-matches")

    items = asyncio.run(_run())
    assert items == []


def test_fetch_items_fixture_search_member_name() -> None:
    """Search by member name (1:1 chat has no topic, falls back to member names)."""

    async def _run() -> list[dict]:
        with patch.dict(os.environ, {"OWA_TUI_FIXTURES": FIXTURE_DIR}):
            screen = TeamsScreen(config={})
            return await screen.fetch_items(search="alice strand")

    items = asyncio.run(_run())
    # Alice Strand appears in all 3 fixture chats (she's a member of each).
    assert len(items) >= 1


def test_fetch_items_annotates_member_names() -> None:
    """Fixture chats without _memberNames get it derived from members field."""
    raw_chat = {
        "id": "19:test@thread.v2",
        "topic": "Test",
        "chatType": "group",
        "members": [
            {"displayName": "Alice Strand", "userId": "u1"},
            {"userId": "u2"},  # no displayName — falls back to userId
        ],
    }
    raw = {"value": [raw_chat]}

    async def _run() -> list[dict]:
        screen = TeamsScreen(config={})
        with (
            patch("owa_tui.fixtures.load", return_value=raw),
        ):
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 1
    names = items[0]["_memberNames"]
    assert "Alice Strand" in names
    assert "u2" in names


def test_fetch_items_does_not_overwrite_existing_member_names() -> None:
    """_memberNames already set in fixture must not be overwritten."""
    raw = {
        "value": [
            {
                "id": "19:x@thread.v2",
                "topic": "Pre-set",
                "chatType": "group",
                "_memberNames": ["Pre-set Name"],
                "members": [{"displayName": "Should Not Appear"}],
            }
        ]
    }

    async def _run() -> list[str]:
        screen = TeamsScreen(config={})
        with patch("owa_tui.fixtures.load", return_value=raw):
            items = await screen.fetch_items()
            return items[0]["_memberNames"]

    names = asyncio.run(_run())
    assert names == ["Pre-set Name"]


def test_fetch_items_no_fixture_mocked_live() -> None:
    """Live path: fetch_items calls httpx and returns normalized chats."""
    live_payload = {
        "value": [
            {
                "id": "19:live@thread.v2",
                "topic": "Live Chat",
                "chatType": "group",
                "members": [{"displayName": "Live User"}],
                "lastUpdatedDateTime": "2026-06-19T10:00:00Z",
            }
        ]
    }

    # Mock the httpx module that is imported lazily inside fetch_items.
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=live_payload)

    mock_client_instance = MagicMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.get = MagicMock(return_value=mock_resp)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client_instance)

    async def _run() -> list[dict]:
        import sys  # noqa: PLC0415

        screen = TeamsScreen(config={})
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="mock-token"),
            patch.dict(sys.modules, {"httpx": mock_httpx}),
        ):
            return await screen.fetch_items()

    items = asyncio.run(_run())
    assert len(items) == 1
    assert items[0]["topic"] == "Live Chat"
    assert items[0]["_memberNames"] == ["Live User"]


def test_fetch_items_no_fixture_empty_value() -> None:
    """fetch_items returns [] when live payload has no value."""
    raw = {"value": []}

    async def _run() -> list[dict]:
        screen = TeamsScreen(config={})
        with patch("owa_tui.fixtures.load", return_value=raw):
            return await screen.fetch_items()

    assert asyncio.run(_run()) == []


# ===========================================================================
# TeamsThreadScreen.fetch_messages unit tests
# ===========================================================================


def test_fetch_messages_per_chat_fixture() -> None:
    """fetch_messages loads teams_<slug>.json when it exists."""
    msgs = _messages(4)
    raw = {"value": msgs}
    chat_id = "19:general-engineering_thread.v2"

    # Slug for that ID: "19_general_engineering_thread_v2"
    async def _run() -> list[dict]:
        screen = TeamsThreadScreen({}, chat_id=chat_id, chat_name="Test")

        def _fake_load(name: str) -> dict | None:
            return raw if name == "teams_19_general_engineering_thread_v2" else None

        with patch("owa_tui.fixtures.load", side_effect=_fake_load):
            return await screen.fetch_messages()

    result = asyncio.run(_run())
    # normalize_chat_messages reverses (oldest-first); but here we read raw messages
    # directly (Graph format) — the screen reverses them
    assert len(result) == 4


def test_fetch_messages_fallback_fixture() -> None:
    """fetch_messages falls back to teams_messages.json when per-chat file absent."""
    msgs = _messages(2)
    raw = {"value": msgs}

    async def _run() -> list[dict]:
        screen = TeamsThreadScreen({}, chat_id="19:unknown@thread.v2", chat_name="Unknown")

        def _fake_load(name: str) -> dict | None:
            return raw if name == "teams_messages" else None

        with patch("owa_tui.fixtures.load", side_effect=_fake_load):
            return await screen.fetch_messages()

    result = asyncio.run(_run())
    assert len(result) == 2


def test_fetch_messages_reversal_oldest_first() -> None:
    """fetch_messages returns oldest-first (reverses the raw list)."""
    msgs = [
        _message(msg_id="newest", created="2026-06-19T10:00:00Z"),
        _message(msg_id="oldest", created="2026-06-19T09:00:00Z"),
    ]
    raw = {"value": msgs}

    async def _run() -> list[str]:
        screen = TeamsThreadScreen({}, chat_id="19:test@thread.v2", chat_name="Test")
        with patch("owa_tui.fixtures.load", return_value=raw):
            result = await screen.fetch_messages()
            return [m["id"] for m in result]

    ids = asyncio.run(_run())
    # reversed: oldest first
    assert ids == ["oldest", "newest"]


def test_fetch_messages_no_fixture_mocked_live() -> None:
    """Live path for fetch_messages: httpx paginated call returns messages."""
    msgs = _messages(3)
    live_payload = {"value": msgs}

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=live_payload)

    mock_client_instance = MagicMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.get = MagicMock(return_value=mock_resp)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client_instance)

    async def _run() -> list[dict]:
        import sys  # noqa: PLC0415

        screen = TeamsThreadScreen({}, chat_id="19:live@thread.v2", chat_name="Live")
        with (
            patch("owa_tui.fixtures.load", return_value=None),
            patch("owa_tui.adapter.access_token_for", return_value="mock-token"),
            patch.dict(sys.modules, {"httpx": mock_httpx}),
        ):
            return await screen.fetch_messages()

    result = asyncio.run(_run())
    assert len(result) == 3


def test_fetch_messages_empty_fixture() -> None:
    async def _run() -> list[dict]:
        screen = TeamsThreadScreen({}, chat_id="19:empty@thread.v2", chat_name="Empty")
        with patch("owa_tui.fixtures.load", return_value={"value": []}):
            return await screen.fetch_messages()

    assert asyncio.run(_run()) == []


# ===========================================================================
# TeamsThreadScreen pilot tests
# ===========================================================================


def test_thread_renders_messages() -> None:
    msgs = _messages(3)

    async def _run() -> bool:
        app = _make_thread_app(initial_messages=msgs)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            screen = pilot.app.screen
            return isinstance(screen, TeamsThreadScreen) and screen._messages == msgs

    assert asyncio.run(_run())


def test_thread_renders_preloaded_initial_messages() -> None:
    msgs = _messages(2)

    async def _run() -> int:
        app = _make_thread_app(initial_messages=msgs)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.15)
            return len(app.screen._messages)

    assert asyncio.run(_run()) == 2


def test_thread_fetch_worker_populates_messages() -> None:
    msgs = _messages(2)

    async def _run() -> int:
        with patch.object(TeamsThreadScreen, "fetch_messages", return_value=msgs):
            app = _make_thread_app()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause(0.3)
                return len(app.screen._messages)

    assert asyncio.run(_run()) == 2


def test_thread_h_pops_back() -> None:
    async def _run() -> str:
        msgs = _messages(2)
        app = _make_thread_app(initial_messages=msgs)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("h")
            await pilot.pause(0.1)
            # After pop we land on the outer test app which has no screen of its own
            return type(pilot.app.screen).__name__

    # After pop, the TeamsThreadScreen is gone
    assert asyncio.run(_run()) != "TeamsThreadScreen"


def test_thread_q_quits() -> None:
    """q calls app.exit() — the app stops running."""

    async def _run() -> bool:
        msgs = _messages(2)
        app = _make_thread_app(initial_messages=msgs)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)
            # app.exit() has been called — is_running becomes False
            return app.is_running

    assert asyncio.run(_run()) is False


# ===========================================================================
# render_row / render_detail / render_message — via screen methods
# ===========================================================================


def test_render_row_via_screen() -> None:
    sc = TeamsScreen()
    row = sc.render_row(_chat(topic="Test", chat_type="group"), 80)
    assert isinstance(row, str)
    assert "Test" in row
    assert "[grp]" in row


def test_render_detail_via_screen() -> None:
    sc = TeamsScreen()
    detail = sc.render_detail(_chat(topic="Engineering"))
    assert isinstance(detail, str)
    assert "Engineering" in detail


def test_render_message_via_screen() -> None:
    sc = TeamsThreadScreen({}, chat_id="19:x@thread.v2", chat_name="X")
    msg = _message(sender_name="Alice", content="Hello")
    rendered = sc.render_message(msg)
    assert "Alice" in rendered
    assert "Hello" in rendered


# ===========================================================================
# menu_config / sort_items / help_text
# ===========================================================================


def test_menu_config_returns_tuple() -> None:
    sc = TeamsScreen()
    title, fields = sc.menu_config()
    assert isinstance(title, str)
    assert "Teams" in title
    assert isinstance(fields, list)


def test_sort_items_newest_first() -> None:
    sc = TeamsScreen()
    chats = [
        _chat(id="a", last_updated="2026-06-15T10:00:00Z"),
        _chat(id="b", last_updated="2026-06-19T10:00:00Z"),
        _chat(id="c", last_updated="2026-06-10T10:00:00Z"),
    ]
    sorted_chats = sc.sort_items(chats)
    assert sorted_chats[0]["id"] == "b"
    assert sorted_chats[-1]["id"] == "c"


def test_help_text_teams() -> None:
    sc = TeamsScreen()
    ht = sc.help_text()
    assert "j" in ht or "move" in ht
    assert "q" in ht or "quit" in ht.lower()


def test_help_text_thread() -> None:
    sc = TeamsThreadScreen({}, chat_id="19:x@thread.v2", chat_name="X")
    ht = sc.help_text()
    assert isinstance(ht, str)
    assert len(ht) > 0


# ===========================================================================
# on_item_activated: pushes TeamsThreadScreen
# ===========================================================================


def test_on_item_activated_pushes_thread() -> None:
    async def _run() -> str:
        app = _make_teams_app(initial_items=_chats(1), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            chat = _chat(id="19:act@thread.v2", topic="Activated Chat")
            with patch.object(TeamsThreadScreen, "fetch_messages", return_value=[]):
                app.screen.on_item_activated(chat)
                await pilot.pause(0.2)
                return type(app.screen).__name__

    assert asyncio.run(_run()) == "TeamsThreadScreen"


def test_on_item_activated_sets_chat_id() -> None:
    async def _run() -> str:
        app = _make_teams_app(initial_items=_chats(1), detail_pane_mode="right")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.1)
            chat = _chat(id="19:specific-id@thread.v2", topic="Specific")
            with patch.object(TeamsThreadScreen, "fetch_messages", return_value=[]):
                app.screen.on_item_activated(chat)
                await pilot.pause(0.2)
                return app.screen._chat_id

    assert asyncio.run(_run()) == "19:specific-id@thread.v2"


# ===========================================================================
# Registration
# ===========================================================================


def test_teams_registered_in_registry() -> None:
    from owa_tui.screens import SCREEN_REGISTRY

    assert "teams" in SCREEN_REGISTRY
    assert SCREEN_REGISTRY["teams"]["label"] == "Teams"
    assert SCREEN_REGISTRY["teams"]["screen_class"] is TeamsScreen


def test_teams_screen_positional_config() -> None:
    """TeamsScreen must accept config as first positional arg (push_tool contract)."""
    screen = TeamsScreen({}, debug=False)
    assert screen is not None


def test_teams_thread_screen_positional_config() -> None:
    """TeamsThreadScreen must accept config as first positional arg."""
    screen = TeamsThreadScreen({}, chat_id="19:x@thread.v2")
    assert screen is not None
