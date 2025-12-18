from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import CalibDataModel, TaskResultModel

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
        fridge_info (dict): The fridge information. e.g. {"fridge1": "info1"}.
        controller_info (dict): The controller information. e.g. {"controller1": "info1"}.
        note (str): The note. e.g. "This is a note".
        tags (list[str]): The tags. e.g. ["tag1", "tag2"].
        message (str): The message. e.g. "This is a message".
        start_at (str): The time when the
        end_at (str): The time when the execution ended.
        elapsed_time (str): The elapsed time.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

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
    controller_info: dict[str, Any] = Field(..., description="The controller information")
    fridge_info: dict[str, Any] = Field(..., description="The fridge information")
    chip_id: str = Field(..., description="The chip ID")
    start_at: str = Field(..., description="The time when the execution started")
    end_at: str = Field(..., description="The time when the execution ended")
    elapsed_time: str = Field(..., description="The elapsed time")
    calib_data: CalibDataModel = Field(..., description="The calibration data")
    message: str = Field(..., description="The message")
    system_info: SystemInfoModel = Field(..., description="The system information")
