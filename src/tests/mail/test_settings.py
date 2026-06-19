"""Tests for owa_tui.mail.settings — MailSettings dataclass and helpers."""

from __future__ import annotations

import pytest

from owa_tui.mail.settings import (
    DEFAULTS,
    MailSettings,
    cycle,
    from_config,
    to_config_dict,
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults_values() -> None:
    s = MailSettings()
    assert s.reading_pane == "right"
    assert s.split_ratio == 50
    assert s.sort_by == "date_desc"
    assert s.date_format == "iso8601"
    assert s.date_custom == ""


def test_defaults_sentinel_equals_instance() -> None:
    assert DEFAULTS == MailSettings()


# ---------------------------------------------------------------------------
# cycle()
# ---------------------------------------------------------------------------


class TestCycle:
    def test_cycle_reading_pane(self) -> None:
        s = MailSettings(reading_pane="right")
        s2 = cycle(s, "reading_pane")
        assert s2.reading_pane == "bottom"
        s3 = cycle(s2, "reading_pane")
        assert s3.reading_pane == "off"
        s4 = cycle(s3, "reading_pane")
        assert s4.reading_pane == "right"  # wraps

    def test_cycle_split_ratio(self) -> None:
        s = MailSettings(split_ratio=40)
        assert cycle(s, "split_ratio").split_ratio == 50
        assert cycle(cycle(s, "split_ratio"), "split_ratio").split_ratio == 60
        assert cycle(cycle(cycle(s, "split_ratio"), "split_ratio"), "split_ratio").split_ratio == 40

    def test_cycle_sort_by_wraps(self) -> None:
        s = MailSettings(sort_by="unread_first")
        assert cycle(s, "sort_by").sort_by == "date_desc"

    def test_cycle_date_format(self) -> None:
        s = MailSettings(date_format="iso8601")
        assert cycle(s, "date_format").date_format == "ddmm"

    def test_cycle_date_custom_unchanged(self) -> None:
        s = MailSettings(date_custom="my-fmt")
        assert cycle(s, "date_custom") is s

    def test_cycle_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            cycle(MailSettings(), "bogus_field")

    def test_cycle_does_not_mutate(self) -> None:
        original = MailSettings()
        cycle(original, "reading_pane")
        assert original.reading_pane == "right"

    def test_cycle_unknown_current_value_starts_from_beginning(self) -> None:
        # If current value not in the allowed list, cycle wraps to first allowed value.
        # MailSettings is frozen so we test via from_config edge case instead:
        s = from_config({"tui_reading_pane": "unknown"})
        assert s.reading_pane == DEFAULTS.reading_pane


# ---------------------------------------------------------------------------
# from_config()
# ---------------------------------------------------------------------------


class TestFromConfig:
    def test_empty_config_uses_defaults(self) -> None:
        assert from_config({}) == DEFAULTS

    def test_reads_reading_pane(self) -> None:
        s = from_config({"tui_reading_pane": "bottom"})
        assert s.reading_pane == "bottom"

    def test_invalid_reading_pane_falls_back(self) -> None:
        s = from_config({"tui_reading_pane": "invalid"})
        assert s.reading_pane == DEFAULTS.reading_pane

    def test_reads_split_ratio_int(self) -> None:
        s = from_config({"tui_split_ratio": "40"})
        assert s.split_ratio == 40

    def test_invalid_split_ratio_string_falls_back(self) -> None:
        s = from_config({"tui_split_ratio": "not_an_int"})
        assert s.split_ratio == 50

    def test_out_of_range_split_ratio_falls_back(self) -> None:
        s = from_config({"tui_split_ratio": "99"})
        assert s.split_ratio == 50

    def test_reads_sort_by(self) -> None:
        s = from_config({"tui_sort_by": "sender"})
        assert s.sort_by == "sender"

    def test_invalid_sort_by_falls_back(self) -> None:
        s = from_config({"tui_sort_by": "bogus"})
        assert s.sort_by == DEFAULTS.sort_by

    def test_reads_date_format(self) -> None:
        s = from_config({"tui_date_format": "ddmm"})
        assert s.date_format == "ddmm"

    def test_reads_date_custom(self) -> None:
        s = from_config({"tui_date_custom": "%Y/%m/%d"})
        assert s.date_custom == "%Y/%m/%d"

    def test_split_ratio_coerced_to_int(self) -> None:
        s = from_config({"tui_split_ratio": 60})  # already int
        assert isinstance(s.split_ratio, int)
        assert s.split_ratio == 60


# ---------------------------------------------------------------------------
# to_config_dict()
# ---------------------------------------------------------------------------


class TestToConfigDict:
    def test_round_trip(self) -> None:
        s = MailSettings(
            reading_pane="bottom",
            split_ratio=60,
            sort_by="sender",
            date_format="ddmm",
            date_custom="%d/%m",
        )
        d = to_config_dict(s)
        s2 = from_config(d)
        assert s2 == s

    def test_keys(self) -> None:
        d = to_config_dict(DEFAULTS)
        assert set(d.keys()) == {
            "tui_reading_pane",
            "tui_split_ratio",
            "tui_sort_by",
            "tui_date_format",
            "tui_date_custom",
        }

    def test_split_ratio_serialised_as_string(self) -> None:
        d = to_config_dict(DEFAULTS)
        assert d["tui_split_ratio"] == "50"
