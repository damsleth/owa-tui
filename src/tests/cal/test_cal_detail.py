"""Unit tests for CalDetailPane render_detail logic.

Mirrors TestRenderDetail from test_tui.py (curses version).
No Pilot / no network calls.
"""

from __future__ import annotations

from owa_tui.screens.cal.detail import _RESPONSE_LABEL, _attendee_line, render_detail

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_EVENT: dict = {
    "id": "evt-001",
    "subject": "Team standup",
    "start": "2026-06-18T09:00:00",
    "end": "2026-06-18T09:30:00",
    "location": "Zoom",
    "showAs": "busy",
    "categories": ["Work"],
    "isAllDay": False,
    "isOrganizer": False,
    "organizer": "Alice <alice@example.com>",
    "attendees": [
        {"name": "Bob", "address": "bob@example.com", "type": "required", "response": "accepted"},
        {"name": "Carol", "address": "carol@example.com", "type": "optional", "response": "tentative"},
    ],
    "body": "Daily sync.\n\nBring updates.",
    "response": "accepted",
}


def _mk(**kw) -> dict:
    return {**FULL_EVENT, **kw}


# ---------------------------------------------------------------------------
# Basic field rendering
# ---------------------------------------------------------------------------


def test_subject_in_detail() -> None:
    lines = render_detail(FULL_EVENT, 80)
    assert "Team standup" in lines[0]


def test_time_range_shown() -> None:
    lines = render_detail(FULL_EVENT, 80)
    joined = "\n".join(lines)
    assert "09:00" in joined
    assert "09:30" in joined


def test_location_shown() -> None:
    lines = render_detail(FULL_EVENT, 80)
    assert any("Location" in l and "Zoom" in l for l in lines)


def test_organizer_shown() -> None:
    lines = render_detail(FULL_EVENT, 80)
    assert any("Organizer" in l and "Alice" in l for l in lines)


def test_body_shown() -> None:
    lines = render_detail(FULL_EVENT, 80)
    assert any("Daily sync" in l for l in lines)


def test_all_day_label() -> None:
    ev = _mk(isAllDay=True, start="2026-06-18T00:00:00")
    lines = render_detail(ev, 80)
    assert any("all-day" in l for l in lines)


def test_returns_list_of_strings() -> None:
    result = render_detail(FULL_EVENT, 80)
    assert isinstance(result, list)
    assert all(isinstance(l, str) for l in result)


def test_full_shows_attendees_organizer_body_response() -> None:
    lines = render_detail(FULL_EVENT, 80, detail="full")
    text = "\n".join(lines)
    assert "Attendees" in text
    assert "Organizer" in text
    assert "Note:" in text
    assert "Response:" in text


def test_basic_omits_rich_fields() -> None:
    lines = render_detail(FULL_EVENT, 80, detail="basic")
    text = "\n".join(lines)
    assert "Attendees" not in text
    assert "Note:" not in text
    assert "Organizer:" not in text
    assert "Response:" not in text


def test_no_id_line() -> None:
    """The detail pane must NOT show an 'ID:' line (regression guard)."""
    lines = render_detail(FULL_EVENT, 80)
    assert not any(l.startswith("ID:") or l.startswith("Id:") for l in lines)


def test_organizer_response_shown_for_organizer() -> None:
    ev = _mk(isOrganizer=True)
    lines = render_detail(ev, 80, detail="full")
    assert any("organizer" in l.lower() and "Response" in l for l in lines)


def test_narrow_width_does_not_raise() -> None:
    """Width 1, 2, 3 must not raise ValueError (textwrap floor)."""
    for w in (1, 2, 3):
        lines = render_detail(FULL_EVENT, w)
        assert isinstance(lines, list)


# ---------------------------------------------------------------------------
# Attendee rendering
# ---------------------------------------------------------------------------


def test_attendee_optional_flagged() -> None:
    lines = render_detail(FULL_EVENT, 80, detail="full")
    assert any("(optional)" in l for l in lines)


def test_attendee_bare_string_shape() -> None:
    ev = _mk(attendees=["bare@example.com"])
    lines = render_detail(ev, 80, detail="full")
    assert any("bare@example.com" in l for l in lines)


def test_attendee_overflow_shown() -> None:
    """More than 12 attendees → '… +N more' line."""
    many = [{"name": f"Person{i}", "address": f"p{i}@x.com", "type": "required",
             "response": "accepted"} for i in range(15)]
    ev = _mk(attendees=many)
    lines = render_detail(ev, 80, detail="full")
    assert any("more" in l and "+" in l for l in lines)


# ---------------------------------------------------------------------------
# _attendee_line
# ---------------------------------------------------------------------------


def test_attendee_line_dict_shape() -> None:
    att = {"name": "Dave", "address": "dave@x.com", "type": "required", "response": "declined"}
    line = _attendee_line(att, 80)
    assert "Dave" in line
    assert "declined" in line
    assert "(optional)" not in line


def test_attendee_line_optional() -> None:
    att = {"name": "Eve", "address": "eve@x.com", "type": "optional", "response": "notresponded"}
    line = _attendee_line(att, 80)
    assert "(optional)" in line


def test_attendee_line_bare_string() -> None:
    line = _attendee_line("simple@example.com", 80)
    assert "simple@example.com" in line


# ---------------------------------------------------------------------------
# Response label mapping
# ---------------------------------------------------------------------------


def test_response_label_all_values() -> None:
    from owa_tui.screens.cal.detail import _response_label

    for raw, expected in _RESPONSE_LABEL.items():
        assert _response_label(raw) == expected, f"failed for {raw!r}"


def test_response_label_case_insensitive() -> None:
    from owa_tui.screens.cal.detail import _response_label

    assert _response_label("Accepted") == "accepted"
    assert _response_label("DECLINED") == "declined"


# ---------------------------------------------------------------------------
# Underline
# ---------------------------------------------------------------------------


def test_underline_under_subject() -> None:
    ev = _mk(subject="Hello")
    lines = render_detail(ev, 80)
    assert lines[1] == "─" * 5


def test_underline_capped_at_width() -> None:
    ev = _mk(subject="A" * 100)
    lines = render_detail(ev, 20)
    assert len(lines[1]) <= 20
