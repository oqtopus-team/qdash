"""Tests for datetime_utils module."""

from datetime import timedelta

import pytest
from qdash.common.datetime_utils import parse_elapsed_time


class TestParseElapsedTime:
    """Tests for parse_elapsed_time function."""

    def test_parse_none(self):
        """Test parsing None returns None."""
        assert parse_elapsed_time(None) is None

    def test_parse_timedelta(self):
        """Test parsing timedelta returns same timedelta."""
        td = timedelta(hours=1, minutes=30)
        assert parse_elapsed_time(td) == td

    def test_parse_empty_string(self):
        """Test parsing empty string returns None."""
        assert parse_elapsed_time("") is None
        assert parse_elapsed_time("  ") is None

    def test_parse_hms_format(self):
        """Test parsing HH:MM:SS format."""
        assert parse_elapsed_time("1:23:45") == timedelta(hours=1, minutes=23, seconds=45)
        assert parse_elapsed_time("0:00:30") == timedelta(seconds=30)
        assert parse_elapsed_time("10:05:00") == timedelta(hours=10, minutes=5)

    def test_parse_ms_format(self):
        """Test parsing MM:SS format."""
        assert parse_elapsed_time("5:30") == timedelta(minutes=5, seconds=30)
        assert parse_elapsed_time("0:45") == timedelta(seconds=45)

    def test_parse_seconds_human_readable(self):
        """Test parsing human-readable seconds format."""
        assert parse_elapsed_time("38 seconds") == timedelta(seconds=38)
        assert parse_elapsed_time("1 second") == timedelta(seconds=1)
        assert parse_elapsed_time("45 secs") == timedelta(seconds=45)
        assert parse_elapsed_time("30 sec") == timedelta(seconds=30)

    def test_parse_minutes_human_readable(self):
        """Test parsing human-readable minutes format."""
        assert parse_elapsed_time("1 minute") == timedelta(minutes=1)
        assert parse_elapsed_time("13 minutes") == timedelta(minutes=13)
        assert parse_elapsed_time("5 mins") == timedelta(minutes=5)
        assert parse_elapsed_time("2 min") == timedelta(minutes=2)

    def test_parse_hours_human_readable(self):
        """Test parsing human-readable hours format."""
        assert parse_elapsed_time("1 hour") == timedelta(hours=1)
        assert parse_elapsed_time("2 hours") == timedelta(hours=2)
        assert parse_elapsed_time("3 hrs") == timedelta(hours=3)
        assert parse_elapsed_time("4 hr") == timedelta(hours=4)

    def test_parse_combined_human_readable(self):
        """Test parsing combined human-readable format."""
        assert parse_elapsed_time("1 hour 30 minutes") == timedelta(hours=1, minutes=30)
        assert parse_elapsed_time("2 hours 15 minutes 30 seconds") == timedelta(
            hours=2, minutes=15, seconds=30
        )

    def test_parse_numeric_string(self):
        """Test parsing plain numeric string as seconds."""
        assert parse_elapsed_time("60") == timedelta(seconds=60)
        assert parse_elapsed_time("3600") == timedelta(seconds=3600)

    def test_parse_case_insensitive(self):
        """Test parsing is case insensitive."""
        assert parse_elapsed_time("1 MINUTE") == timedelta(minutes=1)
        assert parse_elapsed_time("2 Hours") == timedelta(hours=2)
        assert parse_elapsed_time("30 SECONDS") == timedelta(seconds=30)

    def test_parse_invalid_format(self):
        """Test parsing invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid elapsed time format"):
            parse_elapsed_time("invalid")
        with pytest.raises(ValueError, match="Invalid elapsed time format"):
            parse_elapsed_time("abc:def:ghi")
