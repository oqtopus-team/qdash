# dbmodel/execution_history.py
from bunnet import Document
from datamodel.execution import TaskResultModel
from datamodel.system_info import SystemInfoModel
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qcflow.subflow.execution_manager import ExecutionManager


class TaskResult(TaskResultModel):
    """Task result model."""


class SystemInfo(SystemInfoModel):
    """System information model."""


class ExecutionHistoryDocument(Document):
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

    name: str = Field(..., description="The name of the execution")
    execution_id: str = Field(..., description="The execution ID")
    calib_data_path: str = Field(..., description="The path to the calibration data")
    note: dict = Field(..., description="The note")
    status: str = Field(..., description="The status of the execution")
    task_results: dict[str, TaskResult] = Field(..., description="The results of the tasks")
    tags: list[str] = Field(..., description="The tags")
    controller_info: dict = Field(..., description="The controller information")
    fridge_info: dict = Field(..., description="The fridge information")
    chip_id: str = Field(..., description="The chip ID")
    start_at: str = Field(..., description="The time when the execution started")
    end_at: str = Field(..., description="The time when the execution ended")
    elapsed_time: str = Field(..., description="The elapsed time")
    calib_data: dict = Field(..., description="The calibration data")
    message: str = Field(..., description="The message")
    system_info: SystemInfo = Field(..., description="The system information")

    class Settings:
        """Settings for the document."""

        name = "execution_history"
        indexes = [IndexModel([("execution_id", ASCENDING)], unique=True)]

    @classmethod
    def from_execution_manager(
        cls, execution_manager: ExecutionManager
    ) -> "ExecutionHistoryDocument":
        return cls(
            name=execution_manager.name,
            execution_id=execution_manager.execution_id,
            calib_data_path=execution_manager.calib_data_path,
            note=execution_manager.note,
            status=execution_manager.status,
            task_results=execution_manager.task_results,
            tags=execution_manager.tags,
            controller_info=execution_manager.controller_info,
            fridge_info=execution_manager.fridge_info,
            chip_id=execution_manager.chip_id,
            start_at=execution_manager.start_at,
            end_at=execution_manager.end_at,
            elapsed_time=execution_manager.elapsed_time,
            calib_data=execution_manager.calib_data.model_dump(),
            message=execution_manager.message,
            system_info=execution_manager.system_info.model_dump(),
        )

    @classmethod
    def find_by_execution_id(cls, execution_id: str) -> "ExecutionHistoryDocument":
        return cls.find_one({"execution_id": execution_id}).run()

    @classmethod
    def update_document(cls, execution_manager: ExecutionManager) -> "ExecutionHistoryDocument":
        doc = cls.find_by_execution_id(execution_manager.execution_id)
        doc.name = execution_manager.name
        doc.calib_data_path = execution_manager.calib_data_path
        doc.note = execution_manager.note
        doc.status = execution_manager.status
        doc.task_results = execution_manager.task_results
        doc.tags = execution_manager.tags
        doc.controller_info = execution_manager.controller_info
        doc.fridge_info = execution_manager.fridge_info
        doc.chip_id = execution_manager.chip_id
        doc.start_at = execution_manager.start_at
        doc.end_at = execution_manager.end_at
        doc.elapsed_time = execution_manager.elapsed_time
        doc.calib_data = execution_manager.calib_data.model_dump()
        doc.message = execution_manager.message
        doc.system_info = execution_manager.system_info.model_dump()
        return doc.save()

    @classmethod
    def insert_document(cls, execution_manager: ExecutionManager) -> "ExecutionHistoryDocument":
        return cls.from_execution_manager(execution_manager).save()

    model_config = ConfigDict(
        from_attributes=True,
    )
