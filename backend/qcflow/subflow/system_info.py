from datetime import datetime

from pydantic import BaseModel, Field


def current_iso_time() -> str:
    return datetime.now().isoformat()


class SystemInfo(BaseModel):
    """Data model for system information.

    Attributes:
        created_at (str): The time when the system information was created. e.g. "2021-01-01T00:00:00Z".
        updated_at (str): The time when the system information was updated. e.g. "2021-01-01T00:00:00Z".
    """

    created_at: str = Field(
        default_factory=current_iso_time,
        description="The time when the system information was created",
    )
    updated_at: str = Field(
        default_factory=current_iso_time,
        description="The time when the system information was updated",
    )

    def update_time(self):
        self.updated_at = current_iso_time()
