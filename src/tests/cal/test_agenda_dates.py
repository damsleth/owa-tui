"""Agenda rows must render a date for Graph's Z-suffixed timestamps.

datetime.fromisoformat only accepts the trailing Z on 3.11+, and this package
supports 3.10 - where the bare call raised and the date column came out as
nine blanks.
"""

from __future__ import annotations

from owa_tui.screens.cal.agenda import _weekday_date, render_row


def test_weekday_date_accepts_a_z_suffixed_start() -> None:
    assert _weekday_date("2026-06-18T09:00:00Z") == "Thu 06-18"


def test_weekday_date_still_accepts_a_naive_start() -> None:
    assert _weekday_date("2026-06-18T09:00:00") == "Thu 06-18"


def test_weekday_date_blanks_on_garbage() -> None:
    assert _weekday_date("not a timestamp") == "         "


def test_render_row_shows_the_date_for_a_z_suffixed_start() -> None:
    event = {"id": "e1", "subject": "Standup", "start": "2026-06-18T09:00:00Z"}
    assert "Thu 06-18" in render_row(event, 80, show_date=True)
