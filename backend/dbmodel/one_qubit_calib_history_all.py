from datetime import datetime
from typing import Optional

from bunnet import Document
from dbmodel.one_qubit_calib import OneQubitCalibData
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class OneQubitCalibHistoryAllModel(Document):
    label: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    qpu_name: str
    cooling_down_id: int
    one_qubit_calib_data: Optional[OneQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "one_qubit_calib_history_all"
        indexes = [
            IndexModel([("timestamp", ASCENDING), ("label", ASCENDING)], unique=True)
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )
