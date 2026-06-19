"""Graph explorer action implementations.

Action keys: o (open browser), y (yank URL), c (curl command),
m (bookmark), D (debug overlay).

These are pure functions that mutate ``GraphState`` — no Textual imports.
All subprocess calls use ``capture_output=True`` to avoid corrupting the TUI.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from owa_tui.graph.state import GraphState

# Audiences that support Graph Explorer
_GRAPH_EXPLORER_AUDIENCES = frozenset({"graph"})

_GRAPH_EXPLORER_BASE = "https://developer.microsoft.com/graph/graph-explorer?request="


def _build_url_for_state(state: "GraphState", api_base: str) -> str:
    """Reconstruct the full URL for the current state."""
    base = api_base.rstrip("/")
    path_part = (state.path or "").strip("/")
    url = f"{base}/{path_part}" if path_part else base
    if state.query:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{state.query}"
    return url


# ---------------------------------------------------------------------------
# Open browser (o)
# ---------------------------------------------------------------------------


def _silence_os_fds() -> Any:
    """Context manager to silence inherited file descriptors around open."""
    import contextlib
    import os

    @contextlib.contextmanager  # type: ignore[arg-type]
    def _ctx() -> Any:
        # Redirect fd 1/2 to /dev/null around webbrowser.open to avoid
        # corrupting the TUI frame with browser-launch output.
        null_fd = None
        saved_1 = saved_2 = -1
        try:
            null_fd = os.open(os.devnull, os.O_WRONLY)
            saved_1 = os.dup(1)
            saved_2 = os.dup(2)
            os.dup2(null_fd, 1)
            os.dup2(null_fd, 2)
            yield
        finally:
            if saved_1 >= 0:
                os.dup2(saved_1, 1)
                os.close(saved_1)
            if saved_2 >= 0:
                os.dup2(saved_2, 2)
                os.close(saved_2)
            if null_fd is not None:
                os.close(null_fd)

    return _ctx()


def action_open_browser(state: "GraphState", api_base: str) -> None:
    """Open Graph Explorer (graph audience) or set status + no-op (others).

    Uses ``_silence_os_fds()`` around ``webbrowser.open`` to avoid corrupting
    the Textual frame.
    """
    if state.audience not in _GRAPH_EXPLORER_AUDIENCES:
        state.status = f"Graph Explorer only available for 'graph' audience (current: {state.audience!r})"
        return

    url = _build_url_for_state(state, api_base)
    # Build Graph Explorer URL
    from urllib.parse import quote

    ge_url = _GRAPH_EXPLORER_BASE + quote(url, safe="")

    import webbrowser

    try:
        with _silence_os_fds():
            result = webbrowser.open(ge_url)
        if result:
            state.status = f"opened Graph Explorer: {ge_url}"
        else:
            state.status = "no browser available"
    except webbrowser.Error:
        state.status = "no browser available"
    except Exception as exc:
        state.status = f"browser error: {exc}"


# ---------------------------------------------------------------------------
# Yank URL (y)
# ---------------------------------------------------------------------------


def action_yank_url(state: "GraphState", api_base: str) -> None:
    """Copy the current URL to the clipboard via pbcopy/xclip/xsel.

    Falls back to setting ``state.status = 'url: <url>'`` if no clipboard
    tool is available.
    """
    url = _build_url_for_state(state, api_base)
    clipboard_cmds = [["pbcopy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for cmd in clipboard_cmds:
        try:
            subprocess.run(
                cmd,
                input=url.encode(),
                capture_output=True,
                check=True,
            )
            state.status = f"yanked: {url}"
            return
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError:
            continue
    # Fallback
    state.status = f"url: {url}"


# ---------------------------------------------------------------------------
# Curl command (c)
# ---------------------------------------------------------------------------


def action_curl_command(state: "GraphState", api_base: str) -> None:
    """Write a curl command (without token) to ``state.stderr_buf``."""
    url = _build_url_for_state(state, api_base)
    curl = f"curl -s '{url}' -H 'Authorization: Bearer <token>'"
    state.stderr_buf += curl + "\n"
    state.status = "curl command added to debug buffer (press D to view)"


# ---------------------------------------------------------------------------
# Bookmark (m)
# ---------------------------------------------------------------------------


def action_bookmark(state: "GraphState", settings: Any) -> None:
    """Add (audience, path) to bookmarks, deduplicating.

    Persists via ``settings.add_bookmark``.
    """
    audience = state.audience
    path = state.path
    label = f"{audience}:{path}"
    if hasattr(settings, "add_bookmark"):
        settings.add_bookmark(audience, path, label)
    state.status = f"bookmarked: {label}"
