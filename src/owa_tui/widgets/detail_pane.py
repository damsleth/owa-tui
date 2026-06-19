"""DetailPane: generic scrollable detail/reading pane."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Static


class DetailPane(ScrollableContainer):
    """Generic scrollable detail pane used by all tool screens.

    Content is set via :meth:`update_content`.  Tool-specific subclasses
    (e.g. ``CalDetailPane``, ``ReaderPane``) inherit from this and add
    tool-specific ``render_*`` methods without duplicating layout logic.

    All theming comes from ``base.tcss`` — no per-widget CSS overrides.
    """

    DEFAULT_CSS = """
    DetailPane {
        overflow-y: scroll;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="detail-content")

    def update_content(self, lines: list[str]) -> None:
        """Replace pane content with *lines* (one Rich markup string per line)."""
        self.query_one("#detail-content", Static).update("\n".join(lines))

    def clear(self) -> None:
        """Clear the pane content."""
        self.update_content([])
