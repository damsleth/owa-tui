"""Tests for the owa-tui launcher: --version, --help, main(), and HomeScreen."""

from __future__ import annotations

import asyncio

import pytest

import owa_tui

# ---------------------------------------------------------------------------
# CLI option tests (no Textual app)
# ---------------------------------------------------------------------------


def test_version_option_reports_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        owa_tui.main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"owa-tui {owa_tui.__version__}\n"


def test_help_option_reports_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        owa_tui.main(["--help"])

    assert exc_info.value.code == 0
    assert "Textual TUI front-end" in capsys.readouterr().out


def test_main_runs_textual_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[owa_tui.OwaTuiApp] = []

    def fake_run(self: owa_tui.OwaTuiApp) -> None:
        calls.append(self)

    monkeypatch.setattr(owa_tui.OwaTuiApp, "run", fake_run)

    owa_tui.main([])

    assert len(calls) == 1


def test_main_passes_tool_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    """--tool flag is forwarded to OwaTuiApp._tool."""
    calls: list[owa_tui.OwaTuiApp] = []

    def fake_run(self: owa_tui.OwaTuiApp) -> None:
        calls.append(self)

    monkeypatch.setattr(owa_tui.OwaTuiApp, "run", fake_run)
    owa_tui.main(["--tool", "cal"])

    assert len(calls) == 1
    assert calls[0]._tool == "cal"


# ---------------------------------------------------------------------------
# HomeScreen Pilot test
# ---------------------------------------------------------------------------


def test_app_starts_with_home_screen() -> None:
    """OwaTuiApp should mount and show the HomeScreen with expected content."""

    async def run_app() -> list[str]:
        app = owa_tui.OwaTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            # HomeScreen should be active
            return [type(s).__name__ for s in app.screen_stack]

    screen_names = asyncio.run(run_app())
    assert "HomeScreen" in screen_names


def test_home_screen_contains_title() -> None:
    """HomeScreen should render the owa-tui title label."""

    async def run_home() -> list[str]:
        app = owa_tui.OwaTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Label

            # Labels live on the active screen, not directly on the app
            return [str(label.render()) for label in app.screen.query(Label)]

    labels = asyncio.run(run_home())
    # At least one label should contain the app title text
    assert any("owa-tui" in lbl for lbl in labels)


def test_push_tool_unknown_key_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    """push_tool with an unknown key should call notify (not crash)."""
    notifications: list[str] = []

    async def run_app() -> None:
        app = owa_tui.OwaTuiApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.notify = lambda msg, **kw: notifications.append(msg)  # type: ignore[method-assign]
            app.push_tool("nonexistent-tool-xyz")

    asyncio.run(run_app())
    assert any("nonexistent-tool-xyz" in n for n in notifications)


# ---------------------------------------------------------------------------
# Transparency toggle (Ctrl+T)
# ---------------------------------------------------------------------------


def test_toggle_transparency_round_trips() -> None:
    """Ctrl+T swaps to an ANSI (terminal-background) theme and back."""

    async def _run() -> tuple[str, str, str]:
        app = owa_tui.OwaTuiApp(config={})
        async with app.run_test() as pilot:
            await pilot.pause()
            start = app.theme
            app.action_toggle_transparency()
            await pilot.pause()
            on = app.theme
            app.action_toggle_transparency()
            await pilot.pause()
            off = app.theme
            return start, on, off

    start, on, off = asyncio.run(_run())
    assert on == "ansi-dark"          # transparent theme uses ansi_default bg
    assert off == start               # restored the original theme


def test_load_identity_sets_header_subtitle() -> None:
    """The identity worker writes 'profile · upn' into the header subtitle."""
    from unittest.mock import patch

    async def _run() -> str:
        app = owa_tui.OwaTuiApp(config={})
        async with app.run_test() as pilot:
            await pilot.pause()
            with patch(
                "owa_tui.adapter.current_identity",
                return_value=("crayon", "me@crayon.no"),
            ):
                app._load_identity()  # worker is skipped in on_mount when headless
                await app.workers.wait_for_complete()
                await pilot.pause()
            return app.sub_title

    assert asyncio.run(_run()) == "crayon  ·  me@crayon.no"
