"""Unit tests for PeopleScreen helpers (no Textual pilot needed)."""

from __future__ import annotations

from owa_tui.people.settings import DEFAULTS as SETTINGS_DEFAULTS
from owa_tui.people.settings import PeopleSettings, cycle
from owa_tui.screens.people import _list_row, _render_person_detail, _sort_people

# ---------------------------------------------------------------------------
# _list_row
# ---------------------------------------------------------------------------


def _person(i: int = 0) -> dict:
    return {
        "id": f"p{i}",
        "displayName": f"Person {i}",
        "email": f"person{i}@example.com",
        "jobTitle": f"Engineer {i}",
        "department": f"Dept {i}",
        "companyName": "Example Corp",
        "officeLocation": "Oslo",
        "mobilePhone": "+47 555 0000",
        "businessPhones": ["+47 555 0001"],
        "source": "people",
    }


def test_list_row_includes_name() -> None:
    p = _person(1)
    row = _list_row(p, width=80)
    assert "Person 1" in row


def test_list_row_includes_email() -> None:
    p = _person(1)
    row = _list_row(p, width=80)
    assert "person1@example.com" in row


def test_list_row_truncates_long_name() -> None:
    p = {**_person(0), "displayName": "A" * 200, "email": ""}
    row = _list_row(p, width=80)
    assert len(row) <= 80 + 5  # some slack for trailing spaces


# ---------------------------------------------------------------------------
# _render_person_detail
# ---------------------------------------------------------------------------


def test_render_person_detail_contains_name() -> None:
    p = _person(2)
    detail = _render_person_detail(p)
    assert "Person 2" in detail


def test_render_person_detail_contains_email() -> None:
    p = _person(2)
    detail = _render_person_detail(p)
    assert "person2@example.com" in detail


def test_render_person_detail_contains_title() -> None:
    p = _person(3)
    detail = _render_person_detail(p)
    assert "Engineer 3" in detail


def test_render_person_detail_no_email() -> None:
    p = {**_person(0), "email": ""}
    detail = _render_person_detail(p)
    assert "Email:" not in detail


# ---------------------------------------------------------------------------
# _sort_people
# ---------------------------------------------------------------------------


def test_sort_name_asc() -> None:
    people = [{"displayName": "Zebra"}, {"displayName": "Apple"}, {"displayName": "Mango"}]
    result = _sort_people(people, "name_asc")
    assert [p["displayName"] for p in result] == ["Apple", "Mango", "Zebra"]


def test_sort_name_desc() -> None:
    people = [{"displayName": "Zebra"}, {"displayName": "Apple"}, {"displayName": "Mango"}]
    result = _sort_people(people, "name_desc")
    assert [p["displayName"] for p in result] == ["Zebra", "Mango", "Apple"]


def test_sort_email_asc() -> None:
    people = [{"email": "z@x.com"}, {"email": "a@x.com"}, {"email": "m@x.com"}]
    result = _sort_people(people, "email_asc")
    assert [p["email"] for p in result] == ["a@x.com", "m@x.com", "z@x.com"]


# ---------------------------------------------------------------------------
# PeopleSettings + cycle
# ---------------------------------------------------------------------------


def test_settings_defaults() -> None:
    assert SETTINGS_DEFAULTS == PeopleSettings()


def test_settings_default_detail_pane() -> None:
    assert PeopleSettings().detail_pane == "off"


def test_cycle_detail_pane() -> None:
    s = PeopleSettings(detail_pane="off")
    s2 = cycle(s, "detail_pane")
    assert s2.detail_pane == "right"


def test_cycle_detail_pane_wraps() -> None:
    s = PeopleSettings(detail_pane="bottom")
    s2 = cycle(s, "detail_pane")
    assert s2.detail_pane == "off"


def test_cycle_sort_by() -> None:
    s = PeopleSettings(sort_by="name_asc")
    s2 = cycle(s, "sort_by")
    assert s2.sort_by == "name_desc"


def test_cycle_split_ratio() -> None:
    s = PeopleSettings(split_ratio=40)
    s2 = cycle(s, "split_ratio")
    assert s2.split_ratio == 50


def test_cycle_unknown_field_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        cycle(PeopleSettings(), "nonexistent_field")


def test_cycle_with_invalid_current_value_falls_back_to_first() -> None:
    """If the current value is not in the valid set, cycle falls back to first."""
    # Construct with valid data, then manually create a bad one via dataclasses.replace
    import dataclasses

    bad = dataclasses.replace(PeopleSettings(), detail_pane="invalid_value")
    result = cycle(bad, "detail_pane")
    from owa_tui.people.settings import DETAIL_PANE_VALUES

    assert result.detail_pane == DETAIL_PANE_VALUES[0]


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------


def test_from_config_valid_values() -> None:
    from owa_tui.people.settings import from_config

    s = from_config({"tui_detail_pane": "right", "tui_split_ratio": "60", "tui_sort_by": "name_desc"})
    assert s.detail_pane == "right"
    assert s.split_ratio == 60
    assert s.sort_by == "name_desc"


def test_from_config_invalid_detail_pane_uses_default() -> None:
    from owa_tui.people.settings import from_config

    s = from_config({"tui_detail_pane": "sideways"})
    assert s.detail_pane == SETTINGS_DEFAULTS.detail_pane


def test_from_config_invalid_split_ratio_uses_default() -> None:
    from owa_tui.people.settings import from_config

    s = from_config({"tui_split_ratio": "not-a-number"})
    assert s.split_ratio == SETTINGS_DEFAULTS.split_ratio


def test_from_config_out_of_range_split_ratio_uses_default() -> None:
    from owa_tui.people.settings import from_config

    s = from_config({"tui_split_ratio": "99"})
    assert s.split_ratio == SETTINGS_DEFAULTS.split_ratio


def test_from_config_invalid_sort_by_uses_default() -> None:
    from owa_tui.people.settings import from_config

    s = from_config({"tui_sort_by": "magic_sort"})
    assert s.sort_by == SETTINGS_DEFAULTS.sort_by


def test_from_config_empty_dict_returns_defaults() -> None:
    from owa_tui.people.settings import from_config

    s = from_config({})
    assert s == SETTINGS_DEFAULTS


# ---------------------------------------------------------------------------
# to_config_dict
# ---------------------------------------------------------------------------


def test_to_config_dict_round_trips() -> None:
    from owa_tui.people.settings import from_config, to_config_dict

    s = PeopleSettings(detail_pane="right", split_ratio=60, sort_by="name_desc")
    d = to_config_dict(s)
    assert d["tui_detail_pane"] == "right"
    assert d["tui_split_ratio"] == "60"
    assert d["tui_sort_by"] == "name_desc"
    # Round-trip
    s2 = from_config(d)
    assert s2 == s
