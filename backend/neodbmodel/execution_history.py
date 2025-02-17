from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from ..datamodel.execution import ExecutionModel
from ..datamodel.system_info import SystemInfoModel


class ExecutionHistoryDocument(Document):
    """
    Document for storing execution history

    Attributes:
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

    execution_id: str = Field(..., description="The execution ID")
    status: str = Field(..., description="The status of the execution")
    tasks: dict = Field(..., description="The tasks of the execution")
    calib_data: dict = Field(..., description="The calibration data")
    fridge_info: dict = Field(..., description="The fridge information")
    controller_info: dict = Field(..., description="The controller information")
    note: str = Field(..., description="The note")
    tags: list[str] = Field(..., description="The tags")
    message: str = Field(..., description="The message")
    start_at: str = Field(..., description="The time when the execution started")
    end_at: str = Field(..., description="The time when the execution ended")
    elapsed_time: str = Field(..., description="The elapsed time")

    system_info: SystemInfoModel

    class Settings:
        name = "execution_history"
        indexes = [IndexModel([("execution_id", ASCENDING)], unique=True)]

    @classmethod
    def from_domain(cls, domain: ExecutionModel) -> "ExecutionHistoryDocument":
        return cls(
            **domain.model_dump(),
        )

    def to_domain(self) -> ExecutionModel:
        return ExecutionModel(**self.model_dump())

    model_config = ConfigDict(
        from_attributes=True,
    )
