"""Tests for ExecutionModel datetime handling."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.system_info import SystemInfoModel


class TestExecutionModelDatetimeValidation:
    """Test ExecutionModel datetime field validation."""

    @pytest.fixture
    def minimal_execution_data(self) -> dict[str, Any]:
        """Return minimal data required for ExecutionModel."""
        return {
            "username": "test_user",
            "name": "test_execution",
            "execution_id": "exec-001",
            "calib_data_path": "/path/to/calib",
            "note": {},
            "status": "completed",
            "tags": [],
            "chip_id": "chip-001",
            "message": "",
            "system_info": SystemInfoModel(),
        }

    def test_start_at_from_datetime(self, minimal_execution_data: dict[str, Any]) -> None:
        """Test start_at accepts datetime object."""
        now = datetime.now(timezone.utc)
        model = ExecutionModel(**minimal_execution_data, start_at=now)
        assert model.start_at is not None
        assert model.start_at.tzinfo is not None

    def test_start_at_naive_datetime_becomes_utc(
        self, minimal_execution_data: dict[str, Any]
    ) -> None:
        """Test naive datetime is converted to timezone-aware UTC."""
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        model = ExecutionModel(**minimal_execution_data, start_at=naive_dt)
        assert model.start_at is not None
        assert model.start_at.tzinfo is not None

    def test_start_at_none(self, minimal_execution_data: dict[str, Any]) -> None:
        """Test start_at accepts None."""
        model = ExecutionModel(**minimal_execution_data, start_at=None)
        assert model.start_at is None

    def test_end_at_from_datetime(self, minimal_execution_data: dict[str, Any]) -> None:
        """Test end_at accepts datetime object."""
        now = datetime.now(timezone.utc)
        model = ExecutionModel(**minimal_execution_data, end_at=now)
        assert model.end_at is not None
        assert model.end_at.tzinfo is not None

    def test_elapsed_time_from_timedelta(self, minimal_execution_data: dict[str, Any]) -> None:
        """Test elapsed_time accepts timedelta directly."""
        td = timedelta(hours=1, minutes=30)
        model = ExecutionModel(**minimal_execution_data, elapsed_time=td)
        assert model.elapsed_time == td

    def test_elapsed_time_from_string(self, minimal_execution_data: dict[str, Any]) -> None:
        """Test elapsed_time accepts string format."""
        model = ExecutionModel(
            **minimal_execution_data,
            elapsed_time="1:30:00",  # type: ignore[arg-type]
        )
        assert model.elapsed_time == timedelta(hours=1, minutes=30)

    def test_elapsed_time_from_float(self, minimal_execution_data: dict[str, Any]) -> None:
        """Test elapsed_time accepts float (seconds)."""
        model = ExecutionModel(
            **minimal_execution_data,
            elapsed_time=5400.0,  # type: ignore[arg-type]
        )
        assert model.elapsed_time == timedelta(seconds=5400)

    def test_elapsed_time_none(self, minimal_execution_data: dict[str, Any]) -> None:
        """Test elapsed_time accepts None."""
        model = ExecutionModel(**minimal_execution_data, elapsed_time=None)
        assert model.elapsed_time is None


class TestExecutionModelDatetimeSerialization:
    """Test ExecutionModel datetime serialization."""

    @pytest.fixture
    def execution_model(self) -> ExecutionModel:
        """Return an ExecutionModel with datetime fields set."""
        return ExecutionModel(
            username="test_user",
            name="test_execution",
            execution_id="exec-001",
            calib_data_path="/path/to/calib",
            note={},
            status="completed",
            tags=[],
            chip_id="chip-001",
            start_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            end_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            elapsed_time=timedelta(hours=1, minutes=30),
            message="",
            system_info=SystemInfoModel(),
        )

    def test_serialize_start_at_to_iso(self, execution_model: ExecutionModel) -> None:
        """Test start_at serializes to ISO format."""
        data = execution_model.model_dump(mode="json")
        assert data["start_at"] == "2024-01-15T10:30:00+00:00"

    def test_serialize_end_at_to_iso(self, execution_model: ExecutionModel) -> None:
        """Test end_at serializes to ISO format."""
        data = execution_model.model_dump(mode="json")
        assert data["end_at"] == "2024-01-15T12:00:00+00:00"

    def test_serialize_elapsed_time_to_hms(self, execution_model: ExecutionModel) -> None:
        """Test elapsed_time serializes to H:MM:SS format."""
        data = execution_model.model_dump(mode="json")
        assert data["elapsed_time"] == "1:30:00"

    def test_serialize_none_values(self) -> None:
        """Test None values serialize correctly."""
        model = ExecutionModel(
            username="test_user",
            name="test_execution",
            execution_id="exec-001",
            calib_data_path="/path/to/calib",
            note={},
            status="completed",
            tags=[],
            chip_id="chip-001",
            start_at=None,
            end_at=None,
            elapsed_time=None,
            message="",
            system_info=SystemInfoModel(),
        )
        data = model.model_dump(mode="json")
        assert data["start_at"] is None
        assert data["end_at"] is None
        assert data["elapsed_time"] is None
