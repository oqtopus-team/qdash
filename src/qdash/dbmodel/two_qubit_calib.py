from datetime import datetime
from typing import Optional, Union

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class Data(BaseModel):
    value: Union[float, list, list[list]]
    unit: str
    type: str


class EdgeInfo(BaseModel):
    source: str
    target: str
    size: int
    fill: str


class TwoQubitCalibData(BaseModel):
    cross_resonance_power: Optional[Data] = Field(None)
    average_gate_fidelity: Optional[Data] = Field(None)

    def simplify(self):
        for field in self.__fields__:
            value = getattr(self, field)
            if isinstance(value, Data):
                setattr(self, field, value.value)
            elif isinstance(value, list):
                setattr(
                    self,
                    field,
                    [item.value if isinstance(item, Data) else item for item in value],
                )


class TwoQubitCalibModel(Document):
    qpu_name: str
    cooling_down_id: int
    label: str
    status: str
    edge_info: EdgeInfo
    two_qubit_calib_data: Optional[TwoQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    model_config = ConfigDict(from_attributes=True)

    class Settings:
        name = "two_qubit_calib"
        indexes = [IndexModel([("label", ASCENDING), ("qpu_name", ASCENDING)], unique=True)]
