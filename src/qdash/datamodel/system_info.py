from datetime import datetime

from pydantic import BaseModel, Field, field_serializer
from qdash.common.datetime_utils import now


class SystemInfoModel(BaseModel):
    """Data model for system information.

    Attributes
    ----------
        created_at (datetime): The time when the system information was created.
        updated_at (datetime): The time when the system information was updated.

    """

    created_at: datetime = Field(
        default_factory=now,
        description="The time when the system information was created",
    )
    updated_at: datetime = Field(
        default_factory=now,
        description="The time when the system information was updated",
    )

    @field_serializer("created_at", "updated_at")
    @classmethod
    def _serialize_datetime(cls, v: datetime | None) -> str | None:
        """Serialize datetime to ISO format for JSON compatibility."""
        return v.isoformat() if v else None

    def update_time(self) -> None:
        """Update the time when the system information was updated."""
        self.updated_at = now()
