"""Utility functions and classes for calibration workflows."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from qdash.common.domain.qubit import qid_to_label, qid_to_label_from_chip
from qdash.common.utils.datetime import now

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
