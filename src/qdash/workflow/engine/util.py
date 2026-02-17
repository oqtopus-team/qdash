"""Utility functions and classes for calibration workflows."""

from datetime import datetime
from typing import Any

from prefect import task
from pydantic import BaseModel, Field
from qdash.common.datetime_utils import now
from qdash.common.qubit_utils import qid_to_label, qid_to_label_from_chip
from qdash.datamodel.task import TaskModel
from qdash.workflow.calibtasks.base import BaseTask

__all__ = ["qid_to_label", "qid_to_label_from_chip"]


def get_current_timestamp() -> datetime:
    """Get current timestamp in configured timezone."""
    return now()


def pydantic_serializer(obj: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic BaseModel instance to a dictionary.

    Args:
    ----
        obj (BaseModel): The Pydantic model instance to serialize.

    Returns:
    -------
        dict: The serialized dictionary representation of the model.

    Raises:
    ------
        TypeError: If the object is not a Pydantic BaseModel instance.

    """
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Type {type(obj)} not serializable")


@task
def update_active_tasks(username: str, backend: str) -> list[TaskModel]:
    """Update the active tasks in the registry and return a list of TaskModel instances."""
    task_cls = BaseTask.registry.get(backend)
    if task_cls is None:
        return []
    return [
        TaskModel(
            project_id=None,
            username=username,
            backend=backend,
            name=cls.name,
            description=cls.__doc__ or "",
            task_type=cls.task_type,
            input_parameters={
                name: param.model_dump()
                for name, param in cls.input_parameters.items()
                if param is not None
            },
            output_parameters={
                name: param.model_dump() for name, param in cls.output_parameters.items()
            },
        )
        for cls in task_cls.values()
    ]


class SystemInfo(BaseModel):
    """Data model for system information."""

    created_at: datetime = Field(
        default_factory=get_current_timestamp,
        description="The time when the system information was created",
    )
    updated_at: datetime = Field(
        default_factory=get_current_timestamp,
        description="The time when the system information was updated",
    )

    def update_time(self) -> None:
        """Update the time when the system information was updated."""
        self.updated_at = get_current_timestamp()
