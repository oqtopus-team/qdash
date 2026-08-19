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
        result = TaskResult(elapsed_time=90.5)  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(seconds=90.5)

    def test_elapsed_time_from_int_seconds(self) -> None:
        """Test elapsed_time accepts int (seconds)."""
        result = TaskResult(elapsed_time=3600)  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(hours=1)

    def test_elapsed_time_from_hms_string(self) -> None:
        """Test elapsed_time accepts H:MM:SS string format."""
        result = TaskResult(elapsed_time="1:30:45")  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(hours=1, minutes=30, seconds=45)

    def test_elapsed_time_from_ms_string(self) -> None:
        """Test elapsed_time accepts MM:SS string format."""
        result = TaskResult(elapsed_time="30:45")  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(minutes=30, seconds=45)

    def test_elapsed_time_from_human_readable_seconds(self) -> None:
        """Test elapsed_time accepts '38 seconds' format."""
        result = TaskResult(elapsed_time="38 seconds")  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(seconds=38)

    def test_elapsed_time_from_human_readable_minutes(self) -> None:
        """Test elapsed_time accepts '5 minutes' format."""
        result = TaskResult(elapsed_time="5 minutes")  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(minutes=5)

    def test_elapsed_time_from_human_readable_hours(self) -> None:
        """Test elapsed_time accepts '2 hours' format."""
        result = TaskResult(elapsed_time="2 hours")  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(hours=2)

    def test_elapsed_time_from_combined_human_readable(self) -> None:
        """Test elapsed_time accepts '1 hour 30 minutes' format."""
        result = TaskResult(elapsed_time="1 hour 30 minutes")  # type: ignore[arg-type]
        assert result.elapsed_time == timedelta(hours=1, minutes=30)

    def test_elapsed_time_none(self) -> None:
        """Test elapsed_time accepts None."""
        result = TaskResult(elapsed_time=None)
        assert result.elapsed_time is None

    def test_elapsed_time_invalid_format(self) -> None:
        """Test elapsed_time raises error for invalid format."""
        with pytest.raises(ValueError):
            TaskResult(elapsed_time="invalid format")  # type: ignore[arg-type]


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


class TestTaskResultRunParameters:
    """Test TaskResult run_parameters field."""

    def test_run_parameters_default_none(self) -> None:
        """Test run_parameters defaults to None."""
        result = TaskResult()
        assert result.run_parameters is None

    def test_run_parameters_accepts_dict(self) -> None:
        """Test run_parameters accepts a dict."""
        run_params = {
            "shots": {"value": 1024, "value_type": "int", "unit": "", "description": ""},
            "interval": {"value": 150, "value_type": "int", "unit": "us", "description": ""},
        }
        result = TaskResult(run_parameters=run_params)
        assert result.run_parameters == run_params

    def test_run_parameters_serialization(self) -> None:
        """Test run_parameters is included in model_dump."""
        run_params = {"shots": {"value": 1024}}
        result = TaskResult(run_parameters=run_params)
        data = result.model_dump()
        assert data["run_parameters"] == run_params

    def test_run_parameters_excluded_when_none(self) -> None:
        """Test run_parameters is excluded from serialization when None."""
        result = TaskResult()
        data = result.model_dump(exclude_none=True)
        assert "run_parameters" not in data


class TestTaskResultOutputParameters:
    """Test typed output parameter history metadata."""

    def test_output_parameter_stays_dictionary_compatible(self) -> None:
        result = TaskResult(
            output_parameters={
                "readout_frequency": {
                    "value": 6.123,
                    "unit": "GHz",
                    "previous_database_value": 5.987,
                    "database_updated": True,
                    "legacy_metadata": "preserved",
                }
            }
        )

        assert result.output_parameters is not None
        parameter = result.output_parameters["readout_frequency"]
        assert isinstance(parameter, dict)
        assert parameter.get("previous_database_value") == 5.987
        assert parameter["legacy_metadata"] == "preserved"

    def test_legacy_output_remains_unchanged(self) -> None:
        result = TaskResult(
            output_parameters={
                "frequency": {"value": 5.0, "unit": "GHz"},
                "label": "legacy metadata",
            }
        )

        assert result.output_parameters is not None
        parameter = result.output_parameters["frequency"]
        assert "database_updated" not in parameter
        assert "previous_database_value" not in parameter
        assert result.output_parameters["label"] == "legacy metadata"

    def test_comparison_fields_are_in_json_schema(self) -> None:
        model_schema = TaskResult.model_json_schema()
        schema = str(model_schema)

        assert "previous_database_value" in schema
        assert "database_updated" in schema
        output_schema = model_schema["properties"]["output_parameters"]
        parameter_variants = output_schema["anyOf"][0]["additionalProperties"]["anyOf"]
        assert {"type": "string"} in parameter_variants


class TestTaskResultInputParameters:
    """Test typed input parameter history snapshots."""

    def test_input_parameter_accepts_sweep_values_and_stays_a_dict(self) -> None:
        result = TaskResult(
            input_parameters={
                "frequency_range": {
                    "value": [4.8, 5.0, 5.2],
                    "unit": "GHz",
                    "task_metadata": {"points": 3},
                }
            }
        )

        assert result.input_parameters is not None
        parameter = result.input_parameters["frequency_range"]
        assert isinstance(parameter, dict)
        assert parameter["value"] == [4.8, 5.0, 5.2]
        assert parameter["task_metadata"] == {"points": 3}

    def test_input_fields_are_in_json_schema(self) -> None:
        schema = str(TaskResult.model_json_schema())

        assert "value_type" in schema
        assert "description" in schema
