"""GraphState: mutable state container for the graph explorer screen.

No Textual imports — fully unit-testable without a running app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from owa_tui.graph.auth import TokenInfo


@dataclass
class GraphState:
    """All mutable state for a single graph explorer session.

    Parameters
    ----------
    config:
        owa-tools config dict (passed from ``OwaTuiApp``).
    audience:
        Active FOCI audience key (e.g. ``'graph'``, ``'azure'``).
    path:
        Current API path relative to the audience base URL.
    debug:
        Enable owa-tools debug logging.
    """

    config: dict[str, Any]
    audience: str = "graph"
    path: str = "me"

    # Per-audience token cache: audience -> TokenInfo
    token_cache: dict[str, TokenInfo] = field(default_factory=dict)

    # Current token expiry (seconds since epoch), mirroring cached token
    exp_epoch: int = 0

    # Query parameters appended to the URL (e.g. ``"$select=displayName"``).
    query: str = ""

    # UI state
    status: str = ""
    items: list[Any] = field(default_factory=list)
    selected: int = 0
    top: int = 0

    # Pagination
    next_link: str | None = None
    dirty: bool = True

    # Last raw response payload and classification
    response: Any = None
    kind: str = ""

    # Debug buffer (stderr equivalent)
    stderr_buf: str = ""

    # Navigation history: list of 7-tuples
    # (audience, path, query, selected, top, rows, next_link)
    history: list[tuple[Any, ...]] = field(default_factory=list)

    # Bookmarks: list of (audience, path, label)
    bookmarks: list[tuple[str, str, str]] = field(default_factory=list)

    # Settings (injected after construction)
    debug: bool = False
