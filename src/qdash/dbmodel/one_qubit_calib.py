from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

import numpy as np
from bunnet import Document
from labrad.units import Value as LabradValue
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.dbmodel.qpu import QPUModel


class Data(BaseModel):
    value: Union[float, list, list[list]]
    unit: str
    type: str


class Position(BaseModel):
    x: float
    y: float


class NodeInfo(BaseModel):
    fill: str
    position: Position


class Status(str, Enum):
    SCHEDULED: str = "scheduled"
    RUNNING: str = "running"
    SUCCESS: str = "success"
    FAILED: str = "failed"
    UNKNOWN: str = "unknown"


class OneQubitCalibData(BaseModel):
    resonator_frequency: Optional[Data] = Field(None)
    qubit_frequency: Optional[Data] = Field(None)
    t1: Optional[Data] = Field(None)
    t2_echo: Optional[Data] = Field(None)
    t2_star: Optional[Data] = Field(None)
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


class OneQubitCalibModel(Document):
    qpu_name: str
    cooling_down_id: int
    label: str
    status: str
    node_info: NodeInfo
    one_qubit_calib_data: Optional[OneQubitCalibData]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "one_qubit_calib"
        indexes = [IndexModel([("label", ASCENDING), ("qpu_name", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_qubit_info(cls) -> dict[str, Any]:
        qpu_name = QPUModel.get_active_qpu_name()
        one_qubit_calib_list = cls.find(cls.qpu_name == qpu_name).run()
        return {item.label: item.one_qubit_calib_data.dict() for item in one_qubit_calib_list}

    @classmethod
    def convert_from_json_dict(cls, json_dict: dict) -> dict[str, Any]:
        """Convert json with array and labrad values to normal dict"""
        qubit_dict = {}
        for key, val in json_dict.items():
            if val is None:
                continue
            if val["type"] == "float_value":
                qubit_dict[key] = val["value"]
            elif val["type"] == "complex_array":
                arr = np.array(val["value"])
                if arr.size == 0:
                    qubit_dict[key] = np.array([], dtype=complex)
                    continue
                qubit_dict[key] = arr[0] + 1.0j * arr[1]
            elif val["type"] == "real_array":
                arr = np.array(val["value"])
                if arr.size == 0:
                    qubit_dict[key] = np.array([], dtype=float)
                    continue
                qubit_dict[key] = arr
            elif val["type"] == "labrad_value":
                qubit_dict[key] = LabradValue(val["value"], val["unit"])
            else:
                raise ValueError("invalid type")
        return qubit_dict
