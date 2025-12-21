from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator
from qdash.common.datetime_utils import ensure_timezone, format_elapsed_time, parse_elapsed_time
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import CalibDataModel, TaskResultModel

__all__ = [
    "CalibDataModel",
    "ExecutionModel",
    "ExecutionStatusModel",
    "TaskResultModel",
]

SCHDULED = "scheduled"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
PENDING = "pending"


class ExecutionStatusModel(str, Enum):
    """enum class for the status of the execution."""

    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    COMPLETED = COMPLETED
    FAILED = FAILED


class ExecutionModel(BaseModel):
    """Data model for an execution.

    Attributes
    ----------
        execution_id (str): The execution ID. e.g. "0".
        status (str): The status of the execution. e.g. "completed".
        tasks (dict): The tasks of the execution. e.g. {"task1": "completed"}.
        calib_data (dict): The calibration data. e.g. {"qubit": {"0":{"qubit_frequency": 5.0}}, "coupling": {"0-1": {"coupling_strength": 0.1}}}.

        note (str): The note. e.g. "This is a note".
        tags (list[str]): The tags. e.g. ["tag1", "tag2"].
        message (str): The message. e.g. "This is a message".
        start_at (datetime): The time when the execution started.
        end_at (datetime): The time when the execution ended.
        elapsed_time (timedelta): The elapsed time.
        system_info (SystemInfoModel): The system information.

    """

    project_id: str | None = Field(None, description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the execution")
    name: str = Field(..., description="The name of the execution")
    execution_id: str = Field(..., description="The execution ID")
    calib_data_path: str = Field(..., description="The path to the calibration data")
    note: dict[str, Any] = Field(..., description="The note")
    status: str = Field(..., description="The status of the execution")
    task_results: dict[str, TaskResultModel] = Field(..., description="The results of the tasks")
    tags: list[str] = Field(..., description="The tags")
    chip_id: str = Field(..., description="The chip ID")
    start_at: datetime | None = Field(None, description="The time when the execution started")
    end_at: datetime | None = Field(None, description="The time when the execution ended")
    elapsed_time: timedelta | None = Field(None, description="The elapsed time")
    calib_data: CalibDataModel = Field(..., description="The calibration data")
    message: str = Field(..., description="The message")
    system_info: SystemInfoModel = Field(..., description="The system information")

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def _ensure_timezone(cls, v: Any) -> datetime | Any:
        """Ensure datetime fields are timezone-aware."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return ensure_timezone(v)
        # For other inputs (e.g., strings), let pydantic handle the conversion
        return v

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats."""
        return parse_elapsed_time(v)

    @field_serializer("start_at", "end_at")
    @classmethod
    def _serialize_datetime(cls, v: datetime | None) -> str | None:
        """Serialize datetime to ISO format for JSON compatibility."""
        return v.isoformat() if v else None

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None
