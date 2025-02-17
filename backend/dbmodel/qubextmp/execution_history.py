from bunnet import Document
from pydantic import BaseModel, ConfigDict
from pymongo import ASCENDING, IndexModel

from .system_info import SystemInfo


class BaseExecutionSchema(BaseModel):
    execution_id: str
    status: str
    tasks: dict
    calib_data: dict
    fridge_info: dict
    controller_info: dict
    note: str
    tags: list[str]
    message: str
    start_at: str
    end_at: str
    elapsed_time: str

    system_info: SystemInfo


class ExecutionHistoryDocument(Document):
    execution_id: str
    status: str
    tasks: dict
    calib_data: dict
    fridge_info: dict
    controller_info: dict
    note: str
    tags: list[str]
    message: str
    start_at: str
    end_at: str
    elapsed_time: str

    system_info: SystemInfo

    class Settings:
        name = "execution_history"
        indexes = [IndexModel([("execution_id", ASCENDING)], unique=True)]

    @classmethod
    def from_domain(cls, domain: BaseExecutionSchema) -> "ExecutionHistoryDocument":
        return cls(
            **domain.model_dump(),
        )

    def to_domain(self) -> BaseExecutionSchema:
        return BaseExecutionSchema(**self.model_dump())

    model_config = ConfigDict(
        from_attributes=True,
    )
