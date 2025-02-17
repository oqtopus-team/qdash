from bunnet import Document
from pydantic import BaseModel, ConfigDict
from pymongo import ASCENDING, IndexModel

from .system_info import SystemInfo


class BaseTaskSchema(BaseModel):
    execution_id: str
    qid: str
    type: str
    task_name: str
    upstream_task: str
    status: str
    input_parameter: dict
    output_parameter: dict
    note: str
    tags: list[str]
    figure_path: list[str]
    message: str
    start_at: str
    end_at: str
    elapsed_time: str

    system_info: SystemInfo


class TaskHistoryDocument(Document):
    execution_id: str
    qid: str
    type: str
    task_name: str
    upstream_task: str
    status: str
    input_parameter: dict
    output_parameter: dict
    note: str
    tags: list[str]
    figure_path: list[str]
    message: str
    start_at: str
    end_at: str
    elapsed_time: str

    system_info: SystemInfo

    class Settings:
        name = "task_history"
        indexes = [IndexModel([("qid", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )
