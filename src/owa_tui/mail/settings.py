"""MailSettings dataclass and helpers for the owa-tui mail screen.

Ported from owa_tools/src/owa_mail/tui_settings.py.

Do NOT import owa_core.tui_kit.settings — implement cycle/from_config/
to_config_dict inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from owa_tui.settings_cycle import cycle_value

READING_PANE_VALUES: Final[tuple[str, ...]] = ("right", "bottom", "off")
SPLIT_RATIO_VALUES: Final[tuple[int, ...]] = (40, 50, 60)
SORT_BY_VALUES: Final[tuple[str, ...]] = (
    "date_desc",
    "date_asc",
    "sender",
    "subject",
    "unread_first",
)
DATE_FORMAT_VALUES: Final[tuple[str, ...]] = ("iso8601", "ddmm", "ddmm_hhmm", "custom")

_CONFIG_KEYS: Final[dict[str, str]] = {
    "reading_pane": "tui_reading_pane",
    "split_ratio": "tui_split_ratio",
    "sort_by": "tui_sort_by",
    "date_format": "tui_date_format",
    "date_custom": "tui_date_custom",
}


@dataclass(frozen=True)
class MailSettings:
    """Immutable mail screen settings."""

    reading_pane: str = "right"  # 'right' | 'bottom' | 'off'
    split_ratio: int = 50  # 40 | 50 | 60  (% for the list pane)
    sort_by: str = "date_desc"
    date_format: str = "iso8601"
    date_custom: str = ""


DEFAULTS = MailSettings()


def cycle(settings: MailSettings, field: str, direction: int = 1) -> MailSettings:
    """Return a new MailSettings with *field* advanced by *direction* (±1).

    ``date_custom`` is free-text and cannot be cycled — returns *settings*
    unchanged.  Unknown *field* raises ``ValueError``.
    """
    if field == "date_custom":
        return settings

    if field == "reading_pane":
        vals: tuple = READING_PANE_VALUES
        current = settings.reading_pane
    elif field == "split_ratio":
        vals = SPLIT_RATIO_VALUES
        current = settings.split_ratio
    elif field == "sort_by":
        vals = SORT_BY_VALUES
        current = settings.sort_by
    elif field == "date_format":
        vals = DATE_FORMAT_VALUES
        current = settings.date_format
    else:
        raise ValueError(f"Unknown MailSettings field: {field!r}")

    next_val = cycle_value(current, vals, direction)
    return dataclasses_replace(settings, **{field: next_val})


def from_config(config: dict) -> MailSettings:
    """Build a MailSettings from a raw config dict.

    Unknown/invalid values fall back to MailSettings defaults.
    ``split_ratio`` is coerced to int; invalid string or out-of-range
    value falls back to 50.
    """
    reading_pane = config.get("tui_reading_pane", DEFAULTS.reading_pane)
    if reading_pane not in READING_PANE_VALUES:
        reading_pane = DEFAULTS.reading_pane

    raw_ratio = config.get("tui_split_ratio", DEFAULTS.split_ratio)
    try:
        split_ratio = int(raw_ratio)
        if split_ratio not in SPLIT_RATIO_VALUES:
            split_ratio = DEFAULTS.split_ratio
    except (ValueError, TypeError):
        split_ratio = DEFAULTS.split_ratio

    sort_by = config.get("tui_sort_by", DEFAULTS.sort_by)
    if sort_by not in SORT_BY_VALUES:
        sort_by = DEFAULTS.sort_by

    date_format = config.get("tui_date_format", DEFAULTS.date_format)
    if date_format not in DATE_FORMAT_VALUES:
        date_format = DEFAULTS.date_format

    date_custom = config.get("tui_date_custom", DEFAULTS.date_custom)

    return MailSettings(
        reading_pane=reading_pane,
        split_ratio=split_ratio,
        sort_by=sort_by,
        date_format=date_format,
        date_custom=date_custom,
    )


def to_config_dict(settings: MailSettings) -> dict[str, str]:
    """Serialise to config dict with tui_* keys."""
    return {
        "tui_reading_pane": settings.reading_pane,
        "tui_split_ratio": str(settings.split_ratio),
        "tui_sort_by": settings.sort_by,
        "tui_date_format": settings.date_format,
        "tui_date_custom": settings.date_custom,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


def dataclasses_replace(obj: MailSettings, **changes) -> MailSettings:
    """Return a new MailSettings replacing *changes* fields."""
    import dataclasses

    return dataclasses.replace(obj, **changes)
