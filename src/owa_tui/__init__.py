"""Textual TUI front-end for the owa-tools Microsoft 365 CLI suite."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from textual.app import App, ComposeResult
from textual.containers import Center, Middle
from textual.widgets import Footer, Header, Label

__version__ = "0.1.0"


class OwaTuiApp(App[None]):
    """Minimal launcher shell for the owa-tools TUI."""

    TITLE = "owa-tui"
    SUB_TITLE = "Microsoft 365 terminal UI"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        """Build the initial placeholder screen without making live service calls."""
        yield Header()
        with Center(), Middle():
            yield Label("owa-tui")
            yield Label("Calendar, mail, and graph screens are under active development.")
            yield Label("Press q to quit.")
        yield Footer()


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser used by the console script."""
    parser = argparse.ArgumentParser(
        prog="owa-tui",
        description="Textual TUI front-end for the owa-tools Microsoft 365 CLI suite.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the owa-tui application."""
    build_parser().parse_args(argv)
    OwaTuiApp().run()
