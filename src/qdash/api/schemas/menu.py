from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Mode(Enum):
    DEFAULT: str = "default"
    DRAG: str = "drag"
    FILTER: str = "filter"
    CUSTOM: str = "custom"


class BaseMenu(BaseModel):
    """
    Represents a base menu.

    Attributes:
        name (str): The name of the menu.
        description (str): The description of the menu.
        plan (list[list[int]]): The plan for the menu.
        mux_index_list (list[int]): The mux index list for the menu.
        mode (str): The mode of the menu.
        notify_bool (bool, optional): Whether to notify or not. Defaults to True.
        flow (list[str]): The flow of the menu.
        exp_list (list[str], optional): The list of experiments. Defaults to None.
    """

    name: str
    description: str
    one_qubit_calib_plan: list[list[int]]
    two_qubit_calib_plan: list[list[tuple[int, int]]]
    mode: str
    notify_bool: bool = True
    flow: list[str]
    exp_list: Optional[list[str]] = Field(default=[])
    tags: Optional[list[str]] = Field(default=[])

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "sample-menu",
                    "description": "menu description",
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


class CreateMenuRequest(BaseMenu):
    pass


class CreateMenuResponse(BaseModel):
    name: str


class DeleteMenuResponse(BaseModel):
    name: str


class UpdateMenuResponse(BaseModel):
    name: str


class UpdateMenuRequest(BaseMenu):
    pass


class ListMenuResponse(BaseMenu):
    pass


class GetMenuResponse(BaseMenu):
    pass
