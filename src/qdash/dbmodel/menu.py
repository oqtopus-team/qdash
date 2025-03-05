from enum import Enum
from typing import Optional

from bunnet import Document
from pydantic import ConfigDict, Field

# OneQubitOperation = int
# TwoQubitOperation = tuple[int, int]

# OneQubitCalibPlan = list[list[OneQubitOperation]]
# TwoQubitCalibPlan = list[list[TwoQubitOperation]]


class Mode(Enum):
    DEFAULT: str = "default"
    DRAG: str = "drag"
    FILTER: str = "filter"
    CUSTOM: str = "custom"


class MenuModel(Document):
    name: str
    description: str
    one_qubit_calib_plan: list[list[int]]
    two_qubit_calib_plan: list[list[tuple[int, int]]]
    mode: str
    notify_bool: bool = True
    flow: list[str]
    exp_list: Optional[list[str]] = Field(default=None, exclude=True)
    tags: Optional[list[str]] = Field(default=None)
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "menu"
