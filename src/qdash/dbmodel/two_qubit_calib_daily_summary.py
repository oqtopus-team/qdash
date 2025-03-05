from typing import Optional

from bunnet import Document
from pydantic import BaseModel, ConfigDict
from pymongo import ASCENDING, IndexModel
from qdash.dbmodel.two_qubit_calib import TwoQubitCalibData


class TwoQubitCalibSummary(BaseModel):
    label: str
    two_qubit_calib_data: Optional[TwoQubitCalibData]


class TwoQubitCalibDailySummaryModel(Document):
    date: str
    labels: list[str]
    qpu_name: str
    cooling_down_id: int
    summary: list[TwoQubitCalibSummary]
    note: str = ""

    class Settings:
        name = "two_qubit_calib_daily_summary"
        indexes = [IndexModel([("date", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )
