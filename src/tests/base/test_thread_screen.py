"""Tests for owa_tui.screens.base.OwaThreadScreen.

Pattern mirrors test_list_screen.py exactly:
  - _FakeThreadScreen is a concrete OwaThreadScreen with canned fetch_messages
    (or a forced error) and a captured render call-log.
  - _make_app() wraps it in a minimal App and push_screen()s it on mount.
  - Tests use asyncio.run(_run()) — no pytest-asyncio, per project convention.
"""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from owa_tui.screens.base.thread import OwaThreadScreen
from owa_tui.widgets.status_bar import StatusBar

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msgs(n: int = 3) -> list[dict]:
    return [
        {
            "id": f"m{i}",
            "from": {"user": {"displayName": f"User {i}"}},
            "createdDateTime": f"2026-06-20T09:0{i}:00Z",
            "body": {"contentType": "text", "content": f"Hello from message {i}"},
        }
        for i in range(n)
    ]


class _FakeThreadScreen(OwaThreadScreen):
    """Concrete OwaThreadScreen for testing base behaviour."""

    def __init__(
        self,
        *,
        fetch_messages_result: list[dict] | None = None,
        fetch_error: str = "",
        **kw: Any,
    ):
        super().__init__(
            None,  # config positional — must be first positional arg
            tool_name="owa-fake-thread",
            audience="graph",
            title="Fake Thread",
            breadcrumb="Chat: Fake",
            **kw,
        )
        self._fetch_messages_result = (
            fetch_messages_result if fetch_messages_result is not None else _msgs()
        )
        self._fetch_error = fetch_error
        self.render_calls: list[dict] = []
        self.loaded_callbacks: list[int] = []

    async def fetch_messages(self) -> list[dict]:
        if self._fetch_error:
            raise RuntimeError(self._fetch_error)
        return list(self._fetch_messages_result)

    def render_message(self, msg: dict) -> str:
        self.render_calls.append(msg)
        sender = (msg.get("from") or {}).get("user", {}).get("displayName", "?")
        content = (msg.get("body") or {}).get("content", "")
        return f"[bold]{sender}[/bold]: {content}"

    def on_messages_loaded(self, messages: list[dict]) -> None:
        self.loaded_callbacks.append(len(messages))


def _make_app(**screen_kw: Any) -> App:
    class _TestApp(App):
        TITLE = "test-thread"

        def compose(self) -> ComposeResult:
            yield Header()
            yield Footer()

        def on_mount(self) -> None:
            self.push_screen(_FakeThreadScreen(**screen_kw))

    return _TestApp()


# ---------------------------------------------------------------------------
# Construction / config positional
# ---------------------------------------------------------------------------


def test_config_positional_is_first_arg() -> None:
    """OwaThreadScreen.__init__ must accept config as a positional argument."""
    sc = _FakeThreadScreen()
    assert sc._config == {}


def test_config_dict_passed_positionally() -> None:
    cfg = {"tenant": "x"}
    sc = OwaThreadScreen.__new__(OwaThreadScreen)
    OwaThreadScreen.__init__(sc, cfg, tool_name="t", audience="graph", title="T")
    assert sc._config is cfg


# ---------------------------------------------------------------------------
# Abstract hook enforcement
# ---------------------------------------------------------------------------


def test_base_fetch_messages_raises_not_implemented() -> None:
    bare = OwaThreadScreen(None, tool_name="t", audience="graph")
    try:
        asyncio.run(bare.fetch_messages())
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError:
        pass


def test_base_render_message_raises_not_implemented() -> None:
    bare = OwaThreadScreen(None, tool_name="t", audience="graph")
    try:
        bare.render_message({})
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError:
        pass


# ---------------------------------------------------------------------------
# Preloaded (initial_messages) path — bypasses worker
# ---------------------------------------------------------------------------


def test_preloaded_messages_render_without_worker() -> None:
    async def _run() -> tuple[int, str, int]:
        app = _make_app(initial_messages=_msgs(4))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            sc: _FakeThreadScreen = app.screen  # type: ignore[assignment]
            return len(sc.render_calls), sc._status, sc.loaded_callbacks[0]

    n_renders, status, loaded_n = asyncio.run(_run())
    assert n_renders == 4
    assert status == "4 messages"
    assert loaded_n == 4


def test_preloaded_empty_shows_zero_status() -> None:
    async def _run() -> str:
        app = _make_app(initial_messages=[])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            return app.screen._status

    assert asyncio.run(_run()) == "0 messages"


# ---------------------------------------------------------------------------
# Fetch worker path
# ---------------------------------------------------------------------------


def test_fetch_worker_populates_log_and_status() -> None:
    async def _run() -> tuple[int, str]:
        app = _make_app(fetch_messages_result=_msgs(3))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.4)
            sc: _FakeThreadScreen = app.screen  # type: ignore[assignment]
            return len(sc._messages), sc._status

    n, status = asyncio.run(_run())
    assert n == 3
    assert status == "3 messages"


def test_fetch_worker_empty_result() -> None:
    async def _run() -> str:
        app = _make_app(fetch_messages_result=[])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.4)
            return app.screen._status

    assert asyncio.run(_run()) == "0 messages"


def test_fetch_worker_error_sets_status() -> None:
    async def _run() -> str:
        app = _make_app(fetch_error="network down")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.4)
            return app.screen._status

    assert asyncio.run(_run()).startswith("error: network down")


# ---------------------------------------------------------------------------
# on_messages_loaded hook
# ---------------------------------------------------------------------------


def test_on_messages_loaded_called_with_correct_count() -> None:
    async def _run() -> list[int]:
        app = _make_app(fetch_messages_result=_msgs(5))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.4)
            return app.screen.loaded_callbacks  # type: ignore[union-attr]

    calls = asyncio.run(_run())
    assert calls == [5]


# ---------------------------------------------------------------------------
# Compose / widget presence
# ---------------------------------------------------------------------------


def test_status_bar_mounts() -> None:
    async def _run() -> int:
        app = _make_app(initial_messages=_msgs(2))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            return len(list(app.screen.query(StatusBar)))

    assert asyncio.run(_run()) >= 1


def test_breadcrumb_label_is_present() -> None:
    async def _run() -> list[str]:
        app = _make_app(initial_messages=_msgs(1))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            from textual.widgets import Label  # noqa: PLC0415

            return [str(lbl.render()) for lbl in app.screen.query(Label) if lbl.id == "thread-breadcrumb"]

    labels = asyncio.run(_run())
    assert any("Fake" in lbl for lbl in labels)


# ---------------------------------------------------------------------------
# Scroll / back / quit key bindings — must not crash
# ---------------------------------------------------------------------------


def test_scroll_keys_do_not_crash() -> None:
    async def _run() -> str:
        app = _make_app(initial_messages=_msgs(6))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            for key in ("j", "k", "j", "j", "d", "u", "g", "G"):
                await pilot.press(key)
                await pilot.pause(0.02)
            return app.screen._status

    status = asyncio.run(_run())
    assert "messages" in status


def test_refresh_action_refetches() -> None:
    async def _run() -> tuple[list[int], str]:
        app = _make_app(fetch_messages_result=_msgs(2))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.4)
            await pilot.press("r")
            await pilot.pause(0.4)
            sc: _FakeThreadScreen = app.screen  # type: ignore[assignment]
            return sc.loaded_callbacks, sc._status

    callbacks, status = asyncio.run(_run())
    # loaded_callbacks is appended by on_messages_loaded: initial + refresh = 2
    assert len(callbacks) >= 2
    assert status == "2 messages"


def test_back_key_pops_screen() -> None:
    async def _run() -> str:
        app = _make_app(initial_messages=_msgs(2))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("h")
            await pilot.pause(0.1)
            # After pop, we are back on the root App screen (no screen stacked)
            return type(app.screen).__name__

    # The root _TestApp composes Header+Footer — app.screen will be the App's
    # default screen, not _FakeThreadScreen.
    name = asyncio.run(_run())
    assert name != "_FakeThreadScreen"


def test_escape_also_pops_screen() -> None:
    async def _run() -> str:
        app = _make_app(initial_messages=_msgs(2))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("escape")
            await pilot.pause(0.1)
            return type(app.screen).__name__

    assert asyncio.run(_run()) != "_FakeThreadScreen"


# ---------------------------------------------------------------------------
# help_text default
# ---------------------------------------------------------------------------


def test_help_text_contains_expected_keys() -> None:
    sc = _FakeThreadScreen(initial_messages=[])
    text = sc.help_text()
    for hint in ("j/k", "g/G", "r", "h", "q"):
        assert hint in text, f"help_text missing '{hint}': {text!r}"
