"""Tests for TaskResult schema datetime handling."""

from datetime import datetime, timedelta, timezone

import pytest
from qdash.api.schemas.task_result import TaskResult


class TestTaskResultElapsedTimeValidation:
    """Test TaskResult elapsed_time field validation."""

    def test_elapsed_time_from_timedelta(self) -> None:
        """Test elapsed_time accepts timedelta directly."""
        result = TaskResult(elapsed_time=timedelta(hours=1, minutes=30, seconds=45))
        assert result.elapsed_time == timedelta(hours=1, minutes=30, seconds=45)

    def test_elapsed_time_from_float_seconds(self) -> None:
        """Test elapsed_time accepts float (seconds)."""
        result = TaskResult(elapsed_time=90.5)
        assert result.elapsed_time == timedelta(seconds=90.5)

    def test_elapsed_time_from_int_seconds(self) -> None:
        """Test elapsed_time accepts int (seconds)."""
        result = TaskResult(elapsed_time=3600)
        assert result.elapsed_time == timedelta(hours=1)

    def test_elapsed_time_from_hms_string(self) -> None:
        """Test elapsed_time accepts H:MM:SS string format."""
        result = TaskResult(elapsed_time="1:30:45")
        assert result.elapsed_time == timedelta(hours=1, minutes=30, seconds=45)

    def test_elapsed_time_from_ms_string(self) -> None:
        """Test elapsed_time accepts MM:SS string format."""
        result = TaskResult(elapsed_time="30:45")
        assert result.elapsed_time == timedelta(minutes=30, seconds=45)

    def test_elapsed_time_from_human_readable_seconds(self) -> None:
        """Test elapsed_time accepts '38 seconds' format."""
        result = TaskResult(elapsed_time="38 seconds")
        assert result.elapsed_time == timedelta(seconds=38)

    def test_elapsed_time_from_human_readable_minutes(self) -> None:
        """Test elapsed_time accepts '5 minutes' format."""
        result = TaskResult(elapsed_time="5 minutes")
        assert result.elapsed_time == timedelta(minutes=5)

    def test_elapsed_time_from_human_readable_hours(self) -> None:
        """Test elapsed_time accepts '2 hours' format."""
        result = TaskResult(elapsed_time="2 hours")
        assert result.elapsed_time == timedelta(hours=2)

    def test_elapsed_time_from_combined_human_readable(self) -> None:
        """Test elapsed_time accepts '1 hour 30 minutes' format."""
        result = TaskResult(elapsed_time="1 hour 30 minutes")
        assert result.elapsed_time == timedelta(hours=1, minutes=30)

    def test_elapsed_time_none(self) -> None:
        """Test elapsed_time accepts None."""
        result = TaskResult(elapsed_time=None)
        assert result.elapsed_time is None

    def test_elapsed_time_invalid_format(self) -> None:
        """Test elapsed_time raises error for invalid format."""
        with pytest.raises(ValueError):
            TaskResult(elapsed_time="invalid format")


class TestTaskResultElapsedTimeSerialization:
    """Test TaskResult elapsed_time serialization."""

    def test_serialize_to_hms_format(self) -> None:
        """Test elapsed_time serializes to H:MM:SS format."""
        result = TaskResult(elapsed_time=timedelta(hours=1, minutes=30, seconds=45))
        data = result.model_dump()
        assert data["elapsed_time"] == "1:30:45"

    def test_serialize_none(self) -> None:
        """Test elapsed_time None serializes to None."""
        result = TaskResult(elapsed_time=None)
        data = result.model_dump()
        assert data["elapsed_time"] is None

    def test_serialize_short_duration(self) -> None:
        """Test elapsed_time short duration serializes correctly."""
        result = TaskResult(elapsed_time=timedelta(seconds=45))
        data = result.model_dump()
        assert data["elapsed_time"] == "0:00:45"


class TestTaskResultDatetimeFields:
    """Test TaskResult datetime field handling."""

    def test_start_at_end_at_datetime(self) -> None:
        """Test start_at and end_at accept datetime objects."""
        now = datetime.now(timezone.utc)
        result = TaskResult(start_at=now, end_at=now)
        assert result.start_at == now
        assert result.end_at == now

    def test_start_at_end_at_none(self) -> None:
        """Test start_at and end_at accept None."""
        result = TaskResult(start_at=None, end_at=None)
        assert result.start_at is None
        assert result.end_at is None

    def test_default_values(self) -> None:
        """Test TaskResult has correct default values."""
        result = TaskResult()
        assert result.task_id is None
        assert result.name == ""
        assert result.status == "pending"
        assert result.default_view is True
        assert result.over_threshold is False
