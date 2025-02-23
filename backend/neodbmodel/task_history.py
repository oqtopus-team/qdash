from typing import ClassVar

from bunnet import Document
from datamodel.system_info import SystemInfoModel
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qcflow.manager.execution import ExecutionManager
from qcflow.manager.task import BaseTaskResult


class SystemInfo(SystemInfoModel):
    """System information model."""


class TaskHistoryDocument(Document):
    """Document for storing execution history.

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

    task_id: str = Field(..., description="The task ID")
    name: str = Field(..., description="The task name")
    upstream_id: str = Field(..., description="The upstream task ID")
    status: str = Field(..., description="The status of the execution")
    message: str = Field(..., description="The message")
    input_parameters: dict = Field(..., description="The input parameters")
    output_parameters: dict = Field(..., description="The output parameters")
    output_parameter_names: list[str] = Field(..., description="The output parameter names")
    note: dict = Field(..., description="The note")
    figure_path: list[str] = Field(..., description="The path to the figure")
    start_at: str = Field(..., description="The time when the execution started")
    end_at: str = Field(..., description="The time when the execution ended")
    elapsed_time: str = Field(..., description="The elapsed time")
    task_type: str = Field(..., description="The task type")
    system_info: SystemInfo = Field(..., description="The system information")
    qid: str = Field("", description="The qubit ID")

    execution_id: str = Field(..., description="The execution ID")
    tags: list[str] = Field(..., description="The tags")
    chip_id: str = Field(..., description="The chip ID")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "task_history"
        indexes: ClassVar = [IndexModel([("task_id", ASCENDING)], unique=True)]

    @classmethod
    def from_manager(
        cls, task: BaseTaskResult, execution_manager: ExecutionManager
    ) -> "TaskHistoryDocument":
        return cls(
            task_id=task.task_id,
            name=task.name,
            upstream_id=task.upstream_id,
            status=task.status,
            message=task.message,
            input_parameters=task.input_parameters,
            output_parameters=task.output_parameters,
            output_parameter_names=task.output_parameter_names,
            note=task.note,
            figure_path=task.figure_path,
            start_at=task.start_at,
            end_at=task.end_at,
            elapsed_time=task.elapsed_time,
            task_type=task.task_type,
            system_info=task.system_info.model_dump(),
            qid=getattr(task, "qid", ""),
            execution_id=execution_manager.execution_id,
            tags=execution_manager.tags,
            chip_id=execution_manager.chip_id,
        )

    @classmethod
    def find_by_task_id(cls, task_id: str) -> "TaskHistoryDocument" | None:  # noqa: TCH010
        return cls.find_one({"task_id": task_id}).run()

    @classmethod
    def upsert_document(
        cls, task: BaseTaskResult, execution_manager: ExecutionManager
    ) -> "TaskHistoryDocument" | None:  # noqa: TCH010
        doc = cls.find_by_task_id(task.task_id)
        if doc:
            doc.delete()
        return cls.from_manager(task=task, execution_manager=execution_manager).save()
