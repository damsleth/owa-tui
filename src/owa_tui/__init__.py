"""Textual TUI front-end for owa-tools Microsoft 365 CLI suite."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

__version__ = "0.1.0"


class OwaTuiApp(App[None]):
    """Single unified owa-tools TUI app with a screen-stack architecture.

    On startup the ``HomeScreen`` is pushed (tool selector).  Individual tool
    entrypoints can bypass the selector by passing ``tool='cal'`` etc., which
    causes ``on_mount`` to push the tool's screen directly.

    Parameters
    ----------
    config:
        Optional pre-loaded owa-tools config dict.  When ``None`` the app
        launches without auth (suitable for unit tests and offline UI work).
    tool:
        Optional tool key (``'cal'``, ``'mail'``, ``'graph'``) to push on
        startup, bypassing the ``HomeScreen``.
    debug:
        Pass ``True`` to enable verbose owa-tools API logging.
    """

    TITLE = "owa-tui"
    SUB_TITLE = "Microsoft 365 terminal UI"
    CSS_PATH = "widgets/base.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+t", "toggle_transparency", "Transparent bg"),
    ]

    # ANSI themes use 'ansi_default' for surface/background, i.e. the
    # terminal's own colours — so they render with a transparent background.
    _ANSI_THEME = "ansi-dark"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        tool: str | None = None,
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config: dict[str, Any] = config or {}
        self._tool = tool
        self._debug = debug
        self._theme_before_transparent: str | None = None

    def _persist_app_state(self) -> bool:
        """True when theme persistence should touch ~/.config (skip tests/e2e)."""
        from owa_tui import fixtures  # noqa: PLC0415

        return not self.is_headless and not fixtures.enabled()

    def _restore_theme(self) -> None:
        """Apply the theme saved from a previous session, if any."""
        if not self._persist_app_state():
            return
        from owa_tui import app_config  # noqa: PLC0415

        saved = app_config.load().get("theme")
        if saved and saved in self.available_themes:
            self.theme = saved

    def watch_theme(self, theme: str) -> None:
        """Persist the active theme so it survives across tools and sessions."""
        if not self._persist_app_state():
            return
        from owa_tui import app_config  # noqa: PLC0415

        data = app_config.load()
        data["theme"] = theme
        app_config.save(data)

    def action_toggle_transparency(self) -> None:
        """Toggle a transparent (native terminal) background on and off.

        Swaps to an ANSI theme (whose background is the terminal's own colour)
        and back to whatever theme was active before, independent of the theme
        picker.
        """
        if self.theme == self._ANSI_THEME:
            self.theme = self._theme_before_transparent or "textual-dark"
            self._theme_before_transparent = None
        else:
            self._theme_before_transparent = self.theme
            self.theme = self._ANSI_THEME

    # ------------------------------------------------------------------
    # Composition — minimal shell; screens provide their own Header/Footer
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        """Push the appropriate screen on startup."""
        self._restore_theme()
        if self._tool:
            self.push_tool(self._tool)
        else:
            from owa_tui.screens.home import HomeScreen

            self.push_screen(HomeScreen())

        # Resolve the profile/UPN top row off the UI thread. Skipped under the
        # headless test driver and in fixture mode so neither shells out to
        # owa-piggy.
        from owa_tui import fixtures  # noqa: PLC0415

        if not self.is_headless and not fixtures.enabled():
            self._load_identity()

    @work(thread=True, exclusive=True)
    def _load_identity(self) -> None:
        """Set the header subtitle to ``profile · upn`` (best-effort)."""
        from owa_tui.adapter import current_identity  # noqa: PLC0415

        profile, upn = current_identity(self._config)
        label = "  ·  ".join(part for part in (profile, upn) if part)
        if label:
            self.call_from_thread(setattr, self, "sub_title", label)

    # ------------------------------------------------------------------
    # Public API used by HomeScreen and per-tool entrypoints
    # ------------------------------------------------------------------

    def push_tool(self, key: str) -> None:
        """Push the screen registered for *key*, or log an error if unknown."""
        from owa_tui.screens import get_screen_class

        cls = get_screen_class(key)
        if cls is None:
            self.notify(f"Unknown tool: {key!r}.  No screen registered.", severity="error")
            return
        self.push_screen(cls(self._config, debug=self._debug))  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    # Derive --tool choices from the screen registry so a newly registered tool
    # is launchable without touching this list.
    from owa_tui.screens import SCREEN_REGISTRY, _bootstrap_screens

    _bootstrap_screens()
    tool_choices = list(SCREEN_REGISTRY)

    parser = argparse.ArgumentParser(
        prog="owa-tui",
        description="Textual TUI front-end for the owa-tools Microsoft 365 CLI suite.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debug logging.")
    parser.add_argument(
        "--tool",
        choices=tool_choices,
        default=None,
        help="Launch directly into a specific tool screen.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        metavar="ALIAS",
        help="owa-piggy profile alias to authenticate as (default: the broker's default profile).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Run the owa-tui application."""
    args = build_parser().parse_args(argv)
    config = {"owa_piggy_profile": args.profile} if args.profile else None
    OwaTuiApp(config=config, tool=args.tool, debug=args.debug).run()
