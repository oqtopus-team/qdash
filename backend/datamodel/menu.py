from __future__ import annotations

from pydantic import BaseModel, Field


class MenuModel(BaseModel):
    """Menu model.

    Attributes
    ----------
        name (str): The name of the menu.
        username (str): The username of the user who created
        description (str): Detailed description of the menu.
        cal_plan (list[list[int]]): The calibration plan.
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
