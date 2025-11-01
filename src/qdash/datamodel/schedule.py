"""Schedule and menu models for calibration workflows."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SerialNode(BaseModel):
    """Serial node model."""

    serial: list[ScheduleNode | str]


class ParallelNode(BaseModel):
    """Parallel node model."""

    parallel: list[ScheduleNode | str]


class BatchNode(BaseModel):
    """Batch node model."""

    batch: list[str]


ScheduleNode = SerialNode | ParallelNode | BatchNode


SerialNode.model_rebuild()
ParallelNode.model_rebuild()
BatchNode.model_rebuild()


class MenuModel(BaseModel):
    """Menu model for calibration workflows.

    Attributes
    ----------
        name (str): The name of the menu.
        username (str): The username of the user who created
        description (str): Detailed description of the menu.
        schedule (ScheduleNode): The schedule node.
        notify_bool (bool): The notification boolean.
        tasks (list[str]): The tasks.
        tags (list[str]): The tags.

    """

    name: str
    chip_id: str
    username: str
    description: str
    backend: str = ""
    schedule: ScheduleNode
    notify_bool: bool = False
    tasks: list[str] | None = Field(default=None)
    task_details: dict[str, Any] | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
