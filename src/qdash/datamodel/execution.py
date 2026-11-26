from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from qdash.common.utils.datetime import format_iso
from qdash.datamodel.field_types import ElapsedTime, TimezoneAwareDatetime
from qdash.datamodel.system_info import SystemInfoModel

__all__ = [
    "ExecutionModel",
    "ExecutionStatusModel",
]

SCHDULED = "scheduled"
RUNNING = "running"
CANCELLING = "cancelling"
COMPLETED = "completed"
FAILED = "failed"
PENDING = "pending"
CANCELLED = "cancelled"


class ExecutionStatusModel(str, Enum):
    """enum class for the status of the execution."""

    SCHEDULED = SCHDULED
    RUNNING = RUNNING
    CANCELLING = CANCELLING
    COMPLETED = COMPLETED
    FAILED = FAILED
    CANCELLED = CANCELLED


class ExecutionModel(BaseModel):
    """Data model for execution metadata.

    Note
    ----
        Task results are stored in task_result_history collection.
        Calibration data is managed in-memory by ExecutionStateManager.

    Attributes
    ----------
        execution_id (str): The execution ID. e.g. "0".
        status (str): The status of the execution. e.g. "completed".
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
    tags: list[str] = Field(..., description="The tags")
    chip_id: str = Field(..., description="The chip ID")
    start_at: TimezoneAwareDatetime = Field(None, description="The time when the execution started")
    end_at: TimezoneAwareDatetime = Field(None, description="The time when the execution ended")
    elapsed_time: ElapsedTime = Field(None, description="The elapsed time")
    message: str = Field(..., description="The message")
    system_info: SystemInfoModel = Field(..., description="The system information")

    @field_serializer("start_at", "end_at")
    @classmethod
    def _serialize_datetime(cls, v: datetime | None) -> str | None:
        """Serialize datetime to ISO format for JSON compatibility."""
        return format_iso(v)
