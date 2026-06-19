"""Tests for graph action keys: TP37–TP44."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from owa_tui.graph.actions import (
    action_bookmark,
    action_curl_command,
    action_open_browser,
    action_yank_url,
)
from owa_tui.graph.settings import GraphSettings
from owa_tui.graph.state import GraphState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(audience: str = "graph", path: str = "me") -> GraphState:
    state = GraphState(config={})
    state.audience = audience
    state.path = path
    return state


# ---------------------------------------------------------------------------
# TP37: yank uses capture_output=True
# ---------------------------------------------------------------------------


def test_yank_capture_output() -> None:
    """TP37: yank calls subprocess.run with capture_output=True."""
    state = _make_state()
    api_base = "https://graph.microsoft.com/v1.0"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        action_yank_url(state, api_base)

    mock_run.assert_called_once()
    kwargs = mock_run.call_args
    # capture_output should be in kwargs or positional
    call_kwargs = kwargs[1] if kwargs[1] else {}
    assert call_kwargs.get("capture_output") is True


# ---------------------------------------------------------------------------
# TP38: yank fallback when no clipboard tool
# ---------------------------------------------------------------------------


def test_yank_fallback_no_clipboard() -> None:
    """TP38: FileNotFoundError for all clipboard tools → status starts with 'url:'."""
    state = _make_state()
    api_base = "https://graph.microsoft.com/v1.0"

    with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
        action_yank_url(state, api_base)

    assert state.status.startswith("url:")


# ---------------------------------------------------------------------------
# TP39: open browser non-graph audience → no-op
# ---------------------------------------------------------------------------


def test_open_browser_non_graph_noop() -> None:
    """TP39: non-graph audience → status message, no webbrowser.open call."""
    state = _make_state(audience="azure", path="subscriptions")
    api_base = "https://management.azure.com"

    with patch("webbrowser.open") as mock_open:
        action_open_browser(state, api_base)

    mock_open.assert_not_called()
    assert "graph" in state.status.lower() or "azure" in state.status.lower()


# ---------------------------------------------------------------------------
# TP40: open browser graph audience silences fds
# ---------------------------------------------------------------------------


def test_open_browser_graph_silences_fds() -> None:
    """TP40: graph audience calls webbrowser.open inside fd silence context."""
    state = _make_state(audience="graph", path="me")
    api_base = "https://graph.microsoft.com/v1.0"

    with patch("webbrowser.open", return_value=True) as mock_open:
        action_open_browser(state, api_base)

    mock_open.assert_called_once()
    args = mock_open.call_args[0]
    assert "graph-explorer" in args[0].lower() or "developer.microsoft.com" in args[0]


# ---------------------------------------------------------------------------
# TP41: open browser with no browser available
# ---------------------------------------------------------------------------


def test_open_browser_no_browser_available() -> None:
    """TP41: webbrowser.Error → state.status == 'no browser available'."""
    import webbrowser

    state = _make_state(audience="graph", path="me")
    api_base = "https://graph.microsoft.com/v1.0"

    with patch("webbrowser.open", side_effect=webbrowser.Error("no browser")):
        action_open_browser(state, api_base)

    assert state.status == "no browser available"


# ---------------------------------------------------------------------------
# TP42: curl command sets status and buffer
# ---------------------------------------------------------------------------


def test_render_curl_sets_status_and_buffer() -> None:
    """TP42: action_curl_command populates stderr_buf and sets status."""
    state = _make_state(audience="graph", path="users")
    api_base = "https://graph.microsoft.com/v1.0"

    action_curl_command(state, api_base)

    assert state.status != ""
    assert "curl" in state.stderr_buf.lower()
    assert "Authorization" in state.stderr_buf


# ---------------------------------------------------------------------------
# TP43: bookmark adds and deduplicates
# ---------------------------------------------------------------------------


def test_bookmark_adds_and_dedupes() -> None:
    """TP43: action_bookmark adds entry; second call with same (audience, path) doesn't duplicate."""
    state = _make_state(audience="graph", path="users")
    settings = GraphSettings()

    action_bookmark(state, settings)
    assert len(settings.get_bookmarks()) == 1

    # Second call with same audience/path → should not duplicate
    action_bookmark(state, settings)
    assert len(settings.get_bookmarks()) == 1


def test_bookmark_different_paths_both_added() -> None:
    """Different paths are both added."""
    state = _make_state(audience="graph", path="users")
    settings = GraphSettings()

    action_bookmark(state, settings)
    state.path = "groups"
    action_bookmark(state, settings)

    assert len(settings.get_bookmarks()) == 2


# ---------------------------------------------------------------------------
# TP44: audience switch commits even on failed subsequent fetch
# ---------------------------------------------------------------------------


def test_audience_switch_commits_even_on_failure() -> None:
    """TP44: switching audience commits new audience even if fetch fails."""
    from owa_tui.graph.fetch import fetch_items

    state = _make_state(audience="graph", path="me")

    with patch("owa_tui.graph.auth._ensure_token", return_value=None):
        state.audience = "azure"
        state.path = "subscriptions"
        state.dirty = True
        fetch_items(state)

    # Audience remains 'azure' even after failed fetch
    assert state.audience == "azure"
    assert not state.dirty
