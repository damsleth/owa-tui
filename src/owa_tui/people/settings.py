"""PeopleSettings dataclass and helpers for the owa-tui people screen.

Mirrors owa_tui.mail.settings — same frozen dataclass + cycle/from_config pattern.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Final

DETAIL_PANE_VALUES: Final[tuple[str, ...]] = ("right", "bottom", "off")
SPLIT_RATIO_VALUES: Final[tuple[int, ...]] = (40, 50, 60)
SORT_BY_VALUES: Final[tuple[str, ...]] = ("name_asc", "name_desc", "email_asc")


@dataclass(frozen=True)
class PeopleSettings:
    """Immutable people screen settings."""

    detail_pane: str = "off"   # 'right' | 'bottom' | 'off'
    split_ratio: int = 50      # 40 | 50 | 60  (% for the list pane)
    sort_by: str = "name_asc"


DEFAULTS = PeopleSettings()


def cycle(settings: PeopleSettings, field: str, direction: int = 1) -> PeopleSettings:
    """Return a new PeopleSettings with *field* advanced by *direction* (±1)."""
    if field == "detail_pane":
        vals: tuple = DETAIL_PANE_VALUES
        current = settings.detail_pane
    elif field == "split_ratio":
        vals = SPLIT_RATIO_VALUES
        current = settings.split_ratio
    elif field == "sort_by":
        vals = SORT_BY_VALUES
        current = settings.sort_by
    else:
        raise ValueError(f"Unknown PeopleSettings field: {field!r}")

    try:
        idx = list(vals).index(current)
        next_val = vals[(idx + direction) % len(vals)]
    except ValueError:
        next_val = vals[0]

    return dataclasses.replace(settings, **{field: next_val})


def from_config(config: dict) -> PeopleSettings:
    """Build a PeopleSettings from a raw config dict."""
    detail_pane = config.get("tui_detail_pane", DEFAULTS.detail_pane)
    if detail_pane not in DETAIL_PANE_VALUES:
        detail_pane = DEFAULTS.detail_pane

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

    return PeopleSettings(
        detail_pane=detail_pane,
        split_ratio=split_ratio,
        sort_by=sort_by,
    )


def to_config_dict(settings: PeopleSettings) -> dict[str, str]:
    """Serialise to config dict with tui_* keys."""
    return {
        "tui_detail_pane": settings.detail_pane,
        "tui_split_ratio": str(settings.split_ratio),
        "tui_sort_by": settings.sort_by,
    }
