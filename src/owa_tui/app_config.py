"""App-wide owa-tui config — a tiny JSON file at ~/.config/owa-tui/tui.json.

Holds settings that span every tool screen (currently just the theme). Per-tool
settings still live in each tool's own owa-* config; this is only for the shell.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "owa-tui" / "tui.json"


def load() -> dict[str, Any]:
    try:
        return json.loads(_path().read_text())
    except (OSError, ValueError):
        return {}


def save(data: dict[str, Any]) -> None:
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))
    except OSError:
        pass
