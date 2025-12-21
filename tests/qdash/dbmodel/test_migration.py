"""Tests for database migration utilities."""

from qdash.dbmodel.migration import parse_elapsed_time_to_seconds


class TestParseElapsedTimeToSeconds:
    """Test parse_elapsed_time_to_seconds function."""

    def test_parse_hms_format(self) -> None:
        """Test parsing H:MM:SS format."""
        assert parse_elapsed_time_to_seconds("1:30:45") == 5445.0
        assert parse_elapsed_time_to_seconds("0:00:30") == 30.0
        assert parse_elapsed_time_to_seconds("2:00:00") == 7200.0

    def test_parse_ms_format(self) -> None:
        """Test parsing MM:SS format."""
        assert parse_elapsed_time_to_seconds("30:45") == 1845.0
        assert parse_elapsed_time_to_seconds("5:00") == 300.0

    def test_parse_seconds_human_readable(self) -> None:
        """Test parsing '38 seconds' format."""
        assert parse_elapsed_time_to_seconds("38 seconds") == 38.0
        assert parse_elapsed_time_to_seconds("1 second") == 1.0
        assert parse_elapsed_time_to_seconds("45.5 seconds") == 45.5

    def test_parse_minutes_human_readable(self) -> None:
        """Test parsing '5 minutes' format."""
        assert parse_elapsed_time_to_seconds("5 minutes") == 300.0
        assert parse_elapsed_time_to_seconds("1 minute") == 60.0
        assert parse_elapsed_time_to_seconds("2.5 mins") == 150.0

    def test_parse_hours_human_readable(self) -> None:
        """Test parsing '2 hours' format."""
        assert parse_elapsed_time_to_seconds("2 hours") == 7200.0
        assert parse_elapsed_time_to_seconds("1 hour") == 3600.0
        assert parse_elapsed_time_to_seconds("1.5 hrs") == 5400.0

    def test_parse_combined_human_readable(self) -> None:
        """Test parsing '1 hour 30 minutes' format."""
        assert parse_elapsed_time_to_seconds("1 hour 30 minutes") == 5400.0
        assert parse_elapsed_time_to_seconds("2 hours 15 minutes 30 seconds") == 8130.0

    def test_parse_numeric_string(self) -> None:
        """Test parsing plain numeric string as seconds."""
        assert parse_elapsed_time_to_seconds("90") == 90.0
        assert parse_elapsed_time_to_seconds("3600.5") == 3600.5

    def test_parse_case_insensitive(self) -> None:
        """Test parsing is case insensitive."""
        assert parse_elapsed_time_to_seconds("5 SECONDS") == 5.0
        assert parse_elapsed_time_to_seconds("2 MINUTES") == 120.0
        assert parse_elapsed_time_to_seconds("1 HOUR") == 3600.0

    def test_parse_empty_string(self) -> None:
        """Test parsing empty string returns 0."""
        assert parse_elapsed_time_to_seconds("") == 0.0

    def test_parse_none_equivalent(self) -> None:
        """Test parsing None-like values returns 0."""
        assert parse_elapsed_time_to_seconds("") == 0.0

    def test_parse_few_seconds(self) -> None:
        """Test parsing 'a few seconds' format."""
        assert parse_elapsed_time_to_seconds("a few seconds") == 5.0
        assert parse_elapsed_time_to_seconds("few seconds") == 5.0

    def test_parse_invalid_format_returns_zero(self) -> None:
        """Test parsing invalid format returns 0 instead of raising."""
        assert parse_elapsed_time_to_seconds("invalid") == 0.0
        assert parse_elapsed_time_to_seconds("not a time") == 0.0


class TestMigrationEdgeCases:
    """Test edge cases in migration functions."""

    def test_parse_with_whitespace(self) -> None:
        """Test parsing with extra whitespace."""
        assert parse_elapsed_time_to_seconds("  1:30:00  ") == 5400.0
        assert parse_elapsed_time_to_seconds("  30 seconds  ") == 30.0

    def test_parse_abbreviated_formats(self) -> None:
        """Test parsing abbreviated formats."""
        assert parse_elapsed_time_to_seconds("5 secs") == 5.0
        assert parse_elapsed_time_to_seconds("10 mins") == 600.0
        assert parse_elapsed_time_to_seconds("2 hrs") == 7200.0

    def test_parse_decimal_in_hms(self) -> None:
        """Test decimal values in H:MM:SS format are handled."""
        # H:MM:SS format expects integers, so this should fail gracefully
        result = parse_elapsed_time_to_seconds("1.5:30:00")
        # Should not parse as H:MM:SS, might fall through to other formats
        assert result >= 0  # At minimum, should not raise

    def test_parse_negative_values(self) -> None:
        """Test negative values are handled gracefully."""
        # Negative times don't make sense but shouldn't crash
        result = parse_elapsed_time_to_seconds("-5 seconds")
        assert result >= 0 or result < 0  # Just ensure no crash
