from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Label

import owa_tui


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


def test_app_starts_with_launcher_content() -> None:
    async def run_app() -> list[str]:
        app = owa_tui.OwaTuiApp()
        async with app.run_test():
            return [str(label.render()) for label in app.query(Label)]

    labels = asyncio.run(run_app())

    assert "owa-tui" in labels
    assert "Calendar, mail, and graph screens are under active development." in labels
