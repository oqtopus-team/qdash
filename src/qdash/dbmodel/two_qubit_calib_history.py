from datetime import date, datetime
from typing import Optional

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.dbmodel.two_qubit_calib import TwoQubitCalibData


class TwoQubitCalibHistoryModel(Document):
    label: str
    date: str = Field(default_factory=lambda: date.today().strftime("%Y%m%d"))
    qpu_name: str
    cooling_down_id: int
    two_qubit_calib_data: Optional[TwoQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "two_qubit_calib_history"
        indexes = [IndexModel([("date", ASCENDING), ("label", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )
