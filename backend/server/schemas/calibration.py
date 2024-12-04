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
    name: str
    description: str
    one_qubit_calib_plan: list[list[int]]
    two_qubit_calib_plan: list[list[tuple[int, int]]]
    mode: str
    notify_bool: bool = True
    flow: list[str]
    exp_list: Optional[list[str]] = Field(default=[])
    tags: Optional[list[str]] = Field(default=None)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "1Q-MOCK-DEMO",
                    "description": "one qubit calibration for mock demo",
                    "one_qubit_calib_plan": [[0, 1, 2], [4, 5, 6], [7, 8, 9]],
                    "two_qubit_calib_plan": [
                        [[0, 1], [0, 2], [3, 4]],
                        [[5, 6], [7, 8]],
                    ],
                    "mode": "calib",
                    "notify_bool": False,
                    "flow": ["one-qubit-calibration-flow"],
                    "tags": ["tag1", "tag2"],
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
