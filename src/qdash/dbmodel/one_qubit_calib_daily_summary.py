from typing import Optional

from bunnet import Document
from pydantic import BaseModel, ConfigDict
from pymongo import ASCENDING, IndexModel

from qdash.dbmodel.one_qubit_calib import OneQubitCalibData


class OneQubitCalibSummary(BaseModel):
    label: str
    one_qubit_calib_data: Optional[OneQubitCalibData]


class OneQubitCalibDailySummaryModel(Document):
    date: str
    labels: list[str]
    qpu_name: str
    cooling_down_id: int
    summary: list[OneQubitCalibSummary]
    note: str = ""

    class Settings:
        name = "one_qubit_calib_daily_summary"
        indexes = [IndexModel([("date", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )

    def simplify(self) -> list[dict]:
        simplified_data = []
        for item in self.summary:
            if item.one_qubit_calib_data:
                item.one_qubit_calib_data.simplify()  # 簡略化
                simplified_data.append({"label": item.label, **item.one_qubit_calib_data.dict()})
        return simplified_data
