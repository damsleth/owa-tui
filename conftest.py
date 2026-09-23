"""Pytest bootstrap: expose `src/` for non-installed packages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from owa_tui.widgets.status_bar import StatusBar  # noqa: E402

StatusBar.AUTO_CLEAR = 0  # pilot tests read status text at their own pace

import pytest  # noqa: E402

from owa_tui import screens  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_screen_registry():
    """Tests that register fake tools must not leak them into later tests."""
    saved = dict(screens.SCREEN_REGISTRY)
    yield
    screens.SCREEN_REGISTRY.clear()
    screens.SCREEN_REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def _no_real_config_writes(monkeypatch):
    """Screens persist settings via owa_core.config.save_config; never let a
    test write the user's real ~/.config/owa-* files. Tests that assert on
    the write patch over this."""
    import owa_core.config  # noqa: PLC0415

    monkeypatch.setattr(owa_core.config, "save_config", lambda *a, **k: None)
