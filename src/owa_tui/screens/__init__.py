"""Screen registry and home screen for owa-tui.

Tool screens register themselves here so ``OwaTuiApp`` and ``HomeScreen``
can discover available tools without hard-coding imports.

Registration
------------
Each per-tool screen module calls :func:`register_screen` at import time::

    # in owa_tui/cal/screen.py
    from owa_tui.screens import register_screen

    class CalScreen(Screen):
        ...

    register_screen('cal', 'Calendar', CalScreen)

The ``HomeScreen`` reads ``SCREEN_REGISTRY`` to build the tool selector.

Fallback
--------
If no screens have been registered (e.g. during the D-INT phase before tool
screens are authored), ``HomeScreen`` falls back to a placeholder list so
``OwaTuiApp`` still launches cleanly.
"""

from __future__ import annotations

from typing import Any

# Registry: tool_key -> {label, screen_class}
# Populated by per-tool screen modules via register_screen().
SCREEN_REGISTRY: dict[str, dict[str, Any]] = {}


def register_screen(key: str, label: str, screen_class: type) -> None:
    """Register a tool screen in the global registry.

    Parameters
    ----------
    key:
        Short tool identifier (e.g. ``'cal'``, ``'mail'``).
    label:
        Human-readable label shown in the ``HomeScreen`` selector.
    screen_class:
        The :class:`textual.screen.Screen` subclass to push when selected.
    """
    SCREEN_REGISTRY[key] = {"label": label, "screen_class": screen_class}


def get_screen_class(key: str) -> type | None:
    """Return the screen class for *key*, or ``None`` if not registered."""
    entry = SCREEN_REGISTRY.get(key)
    return entry["screen_class"] if entry else None


def registered_tools() -> list[tuple[str, str]]:
    """Return ``[(key, label), ...]`` for all registered tools, insertion order."""
    return [(k, v["label"]) for k, v in SCREEN_REGISTRY.items()]


def _bootstrap_screens() -> None:
    """Import all tool screen modules so they register themselves.

    CalScreen and MailScreen do not call register_screen at module level, so
    we register them here after importing.  GraphScreen does self-register at
    the bottom of its module, so importing it is sufficient.

    This function is called once at the end of this module; callers do not need
    to invoke it explicitly.
    """
    # --- Calendar ---
    from owa_tui.screens.cal.screen import CalScreen  # noqa: PLC0415

    if "cal" not in SCREEN_REGISTRY:
        register_screen("cal", "Calendar", CalScreen)

    # --- Mail ---
    from owa_tui.screens.mail import MailScreen  # noqa: PLC0415

    if "mail" not in SCREEN_REGISTRY:
        register_screen("mail", "Mail", MailScreen)

    # --- Graph Explorer (self-registers on import) ---
    import owa_tui.screens.graph  # noqa: F401, PLC0415


_bootstrap_screens()
