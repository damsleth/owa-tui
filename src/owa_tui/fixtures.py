"""Offline fixture mode for black-box e2e (tui-test) and demos.

When ``OWA_TUI_FIXTURES`` points at a directory, the fetch layer loads canned
JSON from it instead of calling owa-tools / hitting Graph, and token minting
returns a dummy token. Real screens, normalize, filter and render run
unchanged — only the network call and token mint are swapped out.

Fixture files (all optional; a missing file falls back to the live call):
    cal.json          raw calendarView response  -> normalize_events_detail
    mail.json         raw messages response      -> normalize_messages
    mail_body.json    raw single message         -> normalize_message
    graph/<slug>.json raw Graph response keyed by request path
    graph/default.json fallback for any unmatched Graph path

Mutations (calendar respond, mail mark-read) are no-ops that report success.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# Non-empty so screens don't short-circuit to "auth failed".
TOKEN = "fixture-token"


def _dir() -> Path | None:
    d = os.environ.get("OWA_TUI_FIXTURES")
    return Path(d) if d else None


def enabled() -> bool:
    """True when fixture mode is active (OWA_TUI_FIXTURES is set)."""
    return _dir() is not None


def load(name: str) -> Any:
    """Return parsed JSON from ``<dir>/<name>.json``, or None if unset/missing/bad."""
    d = _dir()
    if d is None:
        return None
    f = d / f"{name}.json"
    try:
        return json.loads(f.read_text()) if f.exists() else None
    except (OSError, ValueError):
        return None


def graph(path: str) -> Any:
    """Return the Graph fixture for ``path`` (slugified), else graph/default."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_") or "root"
    hit = load(f"graph/{slug}")
    return hit if hit is not None else load("graph/default")
