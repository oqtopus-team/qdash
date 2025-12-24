# dbmodel/execution_history.py
from datetime import datetime, timedelta
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field, field_validator
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.common.datetime_utils import ensure_timezone, parse_elapsed_time
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionHistoryDocument(Document):
    """Document for storing execution history metadata.

    Attributes
    ----------
        project_id (str): The owning project identifier.
        execution_id (str): The execution ID. e.g. "0".
        status (str): The status of the execution. e.g. "completed".
        note (str): The note. e.g. "This is a note".
        tags (list[str]): The tags. e.g. ["tag1", "tag2"].
        message (str): The message. e.g. "This is a message".
        start_at (datetime): The time when the execution started.
        end_at (datetime): The time when the execution ended.
        elapsed_time (float): The elapsed time in seconds.
        system_info (SystemInfoModel): The system information.

    Note
    ----
        Task results are stored in task_result_history collection.
        Calibration data is stored in qubit/coupling collections.

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
    start_at: datetime | None = Field(None, description="The time when the execution started")
    end_at: datetime | None = Field(None, description="The time when the execution ended")
    elapsed_time: float | None = Field(None, description="The elapsed time in seconds")
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
    def _parse_elapsed_time(cls, v: Any) -> float | None:
        """Parse elapsed_time from various formats and return seconds."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, timedelta):
            return v.total_seconds()
        td = parse_elapsed_time(v)
        return td.total_seconds() if td else None

    class Settings:
        """Settings for the document."""

        name = "execution_history"
        indexes: ClassVar = [
            IndexModel([("project_id", ASCENDING), ("execution_id", ASCENDING)], unique=True),
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("start_at", DESCENDING)]
            ),
            IndexModel([("project_id", ASCENDING), ("chip_id", ASCENDING)]),
            IndexModel(
                [("project_id", ASCENDING), ("username", ASCENDING), ("start_at", DESCENDING)]
            ),
        ]

    @classmethod
    def from_execution_model(cls, execution_model: ExecutionModel) -> "ExecutionHistoryDocument":
        return cls(
            project_id=execution_model.project_id,
            username=execution_model.username,
            name=execution_model.name,
            execution_id=execution_model.execution_id,
            calib_data_path=execution_model.calib_data_path,
            note=execution_model.note,
            status=execution_model.status,
            tags=execution_model.tags,
            chip_id=execution_model.chip_id,
            start_at=execution_model.start_at,
            end_at=execution_model.end_at,
            elapsed_time=execution_model.elapsed_time,
            message=execution_model.message,
            system_info=execution_model.system_info.model_dump(),
        )

    @classmethod
    def upsert_document(cls, execution_model: ExecutionModel) -> "ExecutionHistoryDocument":
        doc = cls.find_one(
            {"project_id": execution_model.project_id, "execution_id": execution_model.execution_id}
        ).run()
        if doc is None:
            doc = cls.from_execution_model(execution_model)
            doc.save()
            return doc

        doc.project_id = execution_model.project_id
        doc.username = execution_model.username
        doc.name = execution_model.name
        doc.calib_data_path = execution_model.calib_data_path
        doc.note = execution_model.note
        doc.status = execution_model.status
        doc.tags = execution_model.tags
        doc.chip_id = execution_model.chip_id
        doc.start_at = execution_model.start_at
        doc.end_at = execution_model.end_at
        doc.elapsed_time = (
            execution_model.elapsed_time.total_seconds() if execution_model.elapsed_time else None
        )
        doc.message = execution_model.message
        doc.system_info = execution_model.system_info
        doc.save()
        return doc

    model_config = ConfigDict(
        from_attributes=True,
    )
