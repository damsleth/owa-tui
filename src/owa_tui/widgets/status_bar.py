"""StatusBar: reactive status line overlaying the AppHeader identity row."""

from __future__ import annotations

from textual.widgets import Label

from owa_tui import fixtures


class StatusBar(Label):
    """Reactive status line shown on header row 3 of every tool screen.

    Usage
    -----
        class MyScreen(Screen):
            def compose(self) -> ComposeResult:
                ...
                yield StatusBar(id='status-bar')

            def watch__status(self, value: str) -> None:
                self.query_one(StatusBar).update(value)

    The widget is a thin ``Label`` subclass so it inherits all Textual
    reactive-update and styling machinery without extra complexity.  Placement
    and colours come from ``base.tcss`` (docked over the AppHeader identity
    row).  An empty message hides the bar so the identity row shows through;
    a non-empty one auto-clears after ``AUTO_CLEAR`` seconds.
    """

    # Seconds a message stays visible; 0 disables auto-clear (e2e fixtures, tests).
    AUTO_CLEAR: float = 0.0 if fixtures.enabled() else 5.0

    _clear_timer = None

    def on_mount(self) -> None:
        self.update(self.content)

    def update(self, content="", *, layout: bool = True) -> None:  # type: ignore[override]
        super().update(content, layout=layout)
        if not self.is_mounted:
            return
        self.display = bool(str(content).strip())
        if self._clear_timer is not None:
            self._clear_timer.stop()
            self._clear_timer = None
        if self.display and self.AUTO_CLEAR:
            self._clear_timer = self.set_timer(self.AUTO_CLEAR, lambda: self.update(""))
