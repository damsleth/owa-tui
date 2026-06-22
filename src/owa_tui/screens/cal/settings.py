"""CalSettings dataclass — verbatim copy of the owa_cal curses settings model.

Do NOT import from ``owa_cal.tui_settings``; this module is a standalone copy
so that owa-tui only depends on the stable owa-tools library surface.
"""

from __future__ import annotations

import dataclasses
from typing import ClassVar

_ALLOWED: dict[str, tuple[str, ...]] = {
    "reading_pane": ("right", "bottom", "off"),
    "split_ratio": ("40", "50", "60"),
    "day_range": ("today", "week", "month"),
    "show_declined": ("yes", "no"),
    "event_detail": ("full", "basic"),
}

# Maps dataclass field name -> config key used for persistence.
FIELD_TO_KEY: ClassVar[dict[str, str]] = {
    "reading_pane": "tui_reading_pane",
    "split_ratio": "tui_split_ratio",
    "day_range": "tui_day_range",
    "show_declined": "tui_show_declined",
    "event_detail": "tui_event_detail",
}


@dataclasses.dataclass
class CalSettings:
    """Persistent settings for the cal Textual screen."""

    reading_pane: str = "right"  # 'right' | 'bottom' | 'off'
    split_ratio: int = 50  # 40 | 50 | 60
    day_range: str = "today"  # 'today' | 'week' | 'month'
    show_declined: str = "no"  # 'yes' | 'no'
    event_detail: str = "full"  # 'full' | 'basic'

    # ------------------------------------------------------------------
    # Allowed values
    # ------------------------------------------------------------------

    @staticmethod
    def allowed(field: str) -> tuple[str, ...]:
        """Return the allowed value sequence for *field*."""
        return _ALLOWED.get(field, ())

    def cycle(self, field: str, direction: int = 1) -> "CalSettings":
        """Return a new ``CalSettings`` with *field* advanced by *direction* (±1)."""
        allowed = self.allowed(field)
        if not allowed:
            return self
        # split_ratio is stored as int but cycled as strings
        current = str(getattr(self, field))
        try:
            idx = allowed.index(current)
        except ValueError:
            idx = 0
        next_val = allowed[(idx + direction) % len(allowed)]
        # Coerce back to int for split_ratio
        if field == "split_ratio":
            return dataclasses.replace(self, **{field: int(next_val)})
        return dataclasses.replace(self, **{field: next_val})

    # ------------------------------------------------------------------
    # Config persistence helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: dict) -> "CalSettings":
        """Build a ``CalSettings`` from an owa-tools config dict (best-effort)."""
        kwargs: dict = {}
        for field, key in FIELD_TO_KEY.items():
            if key in cfg:
                val = cfg[key]
                if field == "split_ratio":
                    try:
                        val = int(val)
                    except (TypeError, ValueError):
                        val = 50
                kwargs[field] = val
        return cls(**kwargs)

    def to_config_patch(self) -> dict[str, str]:
        """Return a dict of config key -> value suitable for ``save_config``."""
        out: dict[str, str] = {}
        for field, key in FIELD_TO_KEY.items():
            out[key] = str(getattr(self, field))
        return out
