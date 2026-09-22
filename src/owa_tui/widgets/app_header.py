"""AppHeader: permanent block-glyph banner shown at the top of every screen.

Replaces Textual's ``Header`` (whose only job was a one-line title that
varied per tool). Row 3 carries ``v<version>`` and the ``profile · upn``
identity the app resolves at startup; tool identity comes from each screen's
own content. A tab row for switching tools is planned to sit beneath it.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

# ponytail: hand-drawn like cronboard's logo; no figlet dependency.
_LOGO = (
    "            ▌     ▖",
    "▛▌ ▌▌▌ ▀▌ ▄ ▛▘ ▌▌ ▌",
    "▙▌ ▚▞▘ █▌   ▙▖ ▙▌ ▌",
)


class AppHeader(Static):
    DEFAULT_CSS = """
    AppHeader {
        dock: top;
        height: 3;
        width: 1fr;
        color: $primary;
        text-style: bold;
        padding: 0 1;
    }
    """

    def on_mount(self) -> None:
        # Re-render when the identity row arrives from the worker.
        self.watch(self.app, "sub_title", self.refresh)

    def render(self) -> Text:
        from owa_tui import __version__  # noqa: PLC0415

        text = Text("\n".join(_LOGO))
        tail = [f"v{__version__}"]
        if self.app.sub_title and self.app.sub_title != type(self.app).SUB_TITLE:
            tail.append(self.app.sub_title)
        text.append("  " + "  ·  ".join(tail), style="not bold dim")
        return text
