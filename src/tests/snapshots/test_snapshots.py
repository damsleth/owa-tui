"""SVG snapshot tests: catch layout/visual regressions the pilot tests miss.

Update after an intentional visual change:
    .venv/bin/python -m pytest src/tests/snapshots --snapshot-update
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import owa_tui

FIXTURES = Path(__file__).resolve().parents[3] / "e2e" / "fixtures"


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OWA_TUI_FIXTURES", str(FIXTURES))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))  # no user settings leak in
    # owa-tools resolves CONFIG_PATH at import time, so the env var alone is too late.
    for name in ("owa_mail", "owa_people", "owa_drive"):
        cfg = importlib.import_module(f"{name}.config")
        monkeypatch.setattr(cfg, "CONFIG_PATH", tmp_path / name / "config")
    monkeypatch.setattr(owa_tui, "__version__", "0.0.0")  # releases don't churn SVGs


@pytest.mark.parametrize("tool", [None, "mail", "people", "drive"])
def test_snapshot(snap_compare, tool) -> None:
    assert snap_compare(owa_tui.OwaTuiApp(tool=tool), terminal_size=(120, 40))
