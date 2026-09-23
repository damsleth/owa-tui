"""Pytest bootstrap: expose `src/` for non-installed packages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from owa_tui.widgets.status_bar import StatusBar  # noqa: E402

StatusBar.AUTO_CLEAR = 0  # pilot tests read status text at their own pace
