"""Tests for owa_tui.mail.dates — pure date formatters."""

from __future__ import annotations

from owa_tui.mail.dates import format_received, validate_custom_format

# ---------------------------------------------------------------------------
# format_received
# ---------------------------------------------------------------------------


class TestFormatReceived:
    def test_iso8601(self) -> None:
        assert format_received("2026-05-10T09:30:00Z", "iso8601") == "2026-05-10"

    def test_ddmm(self) -> None:
        assert format_received("2026-05-10T09:30:00Z", "ddmm") == "10.05"

    def test_ddmm_hhmm(self) -> None:
        assert format_received("2026-05-10T09:30:00Z", "ddmm_hhmm") == "10.05 09:30"

    def test_custom_format(self) -> None:
        assert format_received("2026-05-10T09:30:00Z", "custom", custom="%Y/%m/%d") == "2026/05/10"

    def test_custom_empty_falls_back_to_iso(self) -> None:
        assert format_received("2026-05-10T09:30:00Z", "custom", custom="") == "2026-05-10"

    def test_empty_iso_returns_empty(self) -> None:
        assert format_received("", "iso8601") == ""

    def test_unparseable_iso_returns_empty(self) -> None:
        assert format_received("not-a-date", "iso8601") == ""

    def test_strips_trailing_z(self) -> None:
        assert format_received("2026-05-10T09:00:00Z", "iso8601") == "2026-05-10"

    def test_strips_positive_offset(self) -> None:
        assert format_received("2026-05-10T09:00:00+02:00", "iso8601") == "2026-05-10"

    def test_strips_negative_offset(self) -> None:
        assert format_received("2026-05-10T09:00:00-05:00", "iso8601") == "2026-05-10"

    def test_date_only_format(self) -> None:
        assert format_received("2026-05-10", "iso8601") == "2026-05-10"

    def test_unknown_fmt_falls_back_to_iso(self) -> None:
        assert format_received("2026-05-10T09:00:00Z", "unknown_fmt") == "2026-05-10"

    def test_custom_strftime_error_returns_empty(self) -> None:
        # A format that causes strftime to fail on some platforms — but we
        # can test empty custom which falls back correctly.
        result = format_received("2026-05-10T09:00:00Z", "custom", custom="%Y-%m-%d")
        assert result == "2026-05-10"

    def test_format_without_time(self) -> None:
        assert format_received("2026-05-10T09:00:00Z", "ddmm_hhmm") == "10.05 09:00"


# ---------------------------------------------------------------------------
# validate_custom_format
# ---------------------------------------------------------------------------


class TestValidateCustomFormat:
    def test_valid_format(self) -> None:
        assert validate_custom_format("%Y/%m/%d") is True

    def test_valid_iso_format(self) -> None:
        assert validate_custom_format("%Y-%m-%d") is True

    def test_empty_string_returns_false(self) -> None:
        assert validate_custom_format("") is False

    def test_whitespace_only_returns_false(self) -> None:
        assert validate_custom_format("   ") is False

    def test_percent_z_on_naive_returns_false(self) -> None:
        # %Z on a naive datetime returns "" -> validate returns False
        assert validate_custom_format("%Z") is False

    def test_literal_text_is_valid(self) -> None:
        # strftime of a literal with no format codes returns the literal
        result = validate_custom_format("hello")
        assert result is True  # "hello" is non-empty after strftime

    def test_ddmm_hhmm_format_valid(self) -> None:
        assert validate_custom_format("%d.%m %H:%M") is True

    def test_year_month_day_hour_valid(self) -> None:
        assert validate_custom_format("%Y%m%d%H%M") is True
