from datetime import datetime
from typing import Generic, Optional, TypeVar

from dbmodel.one_qubit_calib import NodeInfo, OneQubitCalibData
from dbmodel.one_qubit_calib_daily_summary import OneQubitCalibSummary
from dbmodel.two_qubit_calib import EdgeInfo, TwoQubitCalibData
from dbmodel.two_qubit_calib_daily_summary import TwoQubitCalibSummary
from pydantic import BaseModel, Field

T = TypeVar("T")


class OneQubitCalibResponse(BaseModel):
    qpu_name: str
    cooling_down_id: int
    label: str
    status: str
    node_info: NodeInfo
    one_qubit_calib_data: Optional[OneQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class TwoQubitCalibResponse(BaseModel):
    qpu_name: str
    cooling_down_id: int
    label: str
    status: str
    edge_info: EdgeInfo
    two_qubit_calib_data: Optional[TwoQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class OneQubitCalibHistoryResponse(BaseModel):
    qpu_name: str
    cooling_down_id: int
    label: str
    date: str
    one_qubit_calib_data: Optional[OneQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class TwoQubitCalibHistoryResponse(BaseModel):
    qpu_name: str
    cooling_down_id: int
    label: str
    date: str
    two_qubit_calib_data: Optional[TwoQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ExecuteCalibRequest(BaseModel):
    """Menu model.

    Attributes
    ----------
        name (str): The name of the menu.
        username (str): The username of the user who created
        description (str): Detailed description of the menu.
        qids (list[list[str]]): The qubit IDs.
        notify_bool (bool): The notification boolean.
        tasks (list[str]): The tasks.
        tags (list[str]): The tags.

    """

    name: str
    username: str
    description: str
    qids: list[list[str]]
    notify_bool: bool = False
    tasks: list[str] | None = Field(default=None, exclude=True)
    tags: list[str] | None = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "1Q-MOCK-DEMO",
                    "username": "default-user",
                    "description": "one qubit calibration for mock demo",
                    "qids": [["Q1"], ["Q2", "Q3"]],
                    "notify_bool": False,
                    "tasks": ["task1", "task2"],
                    "tags": ["calibration", "demo"],
                },
            ]
        }
    }


class ExecuteCalibResponse(BaseModel):
    flow_run_url: str


class ScheduleCalibRequest(BaseModel):
    menu_name: str
    scheduled: str


class ScheduleCalibResponse(BaseModel):
    menu_name: str
    menu: ExecuteCalibRequest
    description: str
    note: str
    timezone: str
    scheduled_time: str
    flow_run_id: str


class BaseCalibDailySummary(BaseModel, Generic[T]):
    date: str
    labels: list[str]
    qpu_name: str
    cooling_down_id: int
    summary: list[T]
    note: str = ""


class OneQubitCalibDailySummaryRequest(BaseCalibDailySummary[OneQubitCalibSummary]):
    pass


class OneQubitCalibDailySummaryResponse(BaseCalibDailySummary[OneQubitCalibSummary]):
    pass


class TwoQubitCalibDailySummaryRequest(BaseCalibDailySummary[TwoQubitCalibSummary]):
    pass


class TwoQubitCalibDailySummaryResponse(BaseCalibDailySummary[TwoQubitCalibSummary]):
    pass


class OneQubitCalibStatsRequest(BaseModel):
    labels: list[str]


class TwoQubitCalibStatsRequest(BaseModel):
    labels: list[str]


class OneQubitCalibStatsResponse(BaseModel):
    date: str

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    def simplify(self):
        for key, value in self.__dict__.items():
            if isinstance(value, OneQubitCalibData):
                value.simplify()

    def add_stats(self, label: str, stats: OneQubitCalibData):
        setattr(self, label, stats)


class TwoQubitCalibStatsResponse(BaseModel):
    date: str

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    def simplify(self):
        for key, value in self.__dict__.items():
            if isinstance(value, TwoQubitCalibData):
                value.simplify()

    def add_stats(self, label: str, stats: TwoQubitCalibData):
        setattr(self, label, stats)


class OneQubitCalibCWInfo(BaseModel):
    cw_info: dict[str, OneQubitCalibData]
