from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import BaseTaskResultModel


class TaskResultHistoryDocument(Document):
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

    username: str = Field(..., description="The username of the user who created the task")
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
    json_figure_path: list[str] = Field([], description="The path to the JSON figure")
    raw_data_path: list[str] = Field([], description="The path to the raw data")
    start_at: str = Field(..., description="The time when the execution started")
    end_at: str = Field(..., description="The time when the execution ended")
    elapsed_time: str = Field(..., description="The elapsed time")
    task_type: str = Field(..., description="The task type")
    system_info: SystemInfoModel = Field(..., description="The system information")
    qid: str = Field("", description="The qubit ID")

    execution_id: str = Field(..., description="The execution ID")
    tags: list[str] = Field(..., description="The tags")
    chip_id: str = Field(..., description="The chip ID")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "task_result_history"
        indexes: ClassVar = [IndexModel([("task_id", ASCENDING), ("username")], unique=True)]

    @classmethod
    def from_datamodel(cls, task: BaseTaskResultModel, execution_model: ExecutionModel) -> "TaskResultHistoryDocument":
        return cls(
            username=execution_model.username,
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
            json_figure_path=task.json_figure_path,
            raw_data_path=task.raw_data_path,
            start_at=task.start_at,
            end_at=task.end_at,
            elapsed_time=task.elapsed_time,
            task_type=task.task_type,
            system_info=task.system_info.model_dump(),
            qid=getattr(task, "qid", ""),
            execution_id=execution_model.execution_id,
            tags=execution_model.tags,
            chip_id=execution_model.chip_id,
        )

    @classmethod
    def upsert_document(cls, task: BaseTaskResultModel, execution_model: ExecutionModel) -> "TaskResultHistoryDocument":
        doc = cls.find_one({"task_id": task.task_id}).run()
        if doc is None:
            doc = cls.from_datamodel(task=task, execution_model=execution_model)
            doc.save()
            return doc
        doc.username = execution_model.username
        doc.name = task.name
        doc.upstream_id = task.upstream_id
        doc.status = task.status
        doc.message = task.message
        doc.input_parameters = task.input_parameters
        doc.output_parameters = task.output_parameters
        doc.output_parameter_names = task.output_parameter_names
        doc.note = task.note
        doc.figure_path = task.figure_path
        doc.json_figure_path = task.json_figure_path
        doc.raw_data_path = task.raw_data_path
        doc.start_at = task.start_at
        doc.end_at = task.end_at
        doc.elapsed_time = task.elapsed_time
        doc.task_type = task.task_type
        doc.system_info = task.system_info.model_dump()
        doc.qid = getattr(task, "qid", "")
        doc.execution_id = execution_model.execution_id
        doc.tags = execution_model.tags
        doc.chip_id = execution_model.chip_id
        doc.save()
        return doc
