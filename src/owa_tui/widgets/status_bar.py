"""StatusBar: reactive status line at the bottom of every tool screen."""

from __future__ import annotations

from textual.widgets import Label


class StatusBar(Label):
    """Reactive status line displayed at the bottom of every tool screen.

    Usage
    -----
        class MyScreen(Screen):
            def compose(self) -> ComposeResult:
                ...
                yield StatusBar(id='status-bar')

            def watch__status(self, value: str) -> None:
                self.query_one(StatusBar).update(value)

    The widget is a thin ``Label`` subclass so it inherits all Textual
    reactive-update and styling machinery without extra complexity.  Visual
    styling (colours, alignment, border) comes from ``base.tcss``.
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        width: 1fr;
        padding: 0 1;
        color: $text-muted;
    }
    """
