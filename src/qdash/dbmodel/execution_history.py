# dbmodel/execution_history.py
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.datamodel.execution import ExecutionModel, TaskResultModel
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionHistoryDocument(Document):
    """Document for storing execution history.

    Attributes
    ----------
        project_id (str): The owning project identifier.
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

    project_id: str = Field(..., description="Owning project identifier")
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
    calib_data: dict[str, Any] = Field(..., description="The calibration data")
    message: str = Field(..., description="The message")
    system_info: SystemInfoModel = Field(..., description="The system information")

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
            task_results=execution_model.task_results,
            tags=execution_model.tags,
            controller_info=execution_model.controller_info,
            fridge_info=execution_model.fridge_info,
            chip_id=execution_model.chip_id,
            start_at=execution_model.start_at,
            end_at=execution_model.end_at,
            elapsed_time=execution_model.elapsed_time,
            calib_data=execution_model.calib_data.model_dump(),
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

        # Update basic fields
        doc.project_id = execution_model.project_id
        doc.username = execution_model.username
        doc.name = execution_model.name
        doc.calib_data_path = execution_model.calib_data_path
        doc.note = execution_model.note
        doc.status = execution_model.status
        doc.tags = execution_model.tags
        doc.controller_info = execution_model.controller_info
        doc.fridge_info = execution_model.fridge_info
        doc.chip_id = execution_model.chip_id
        doc.start_at = execution_model.start_at
        doc.end_at = execution_model.end_at
        doc.elapsed_time = execution_model.elapsed_time
        doc.message = execution_model.message
        doc.system_info = execution_model.system_info.model_dump()

        # Merge task_results
        for task_id, task_result in execution_model.task_results.items():
            doc.task_results[task_id] = task_result

        # Merge calib_data
        calib_data = execution_model.calib_data.model_dump()
        if "qubit" in calib_data:
            if "qubit" not in doc.calib_data:
                doc.calib_data["qubit"] = {}
            for qid, data in calib_data["qubit"].items():
                if qid not in doc.calib_data["qubit"]:
                    doc.calib_data["qubit"][qid] = {}
                doc.calib_data["qubit"][qid].update(data)

        if "coupling" in calib_data:
            if "coupling" not in doc.calib_data:
                doc.calib_data["coupling"] = {}
            for qid, data in calib_data["coupling"].items():
                if qid not in doc.calib_data["coupling"]:
                    doc.calib_data["coupling"][qid] = {}
                doc.calib_data["coupling"][qid].update(data)

        doc.save()
        return doc

    model_config = ConfigDict(
        from_attributes=True,
    )
