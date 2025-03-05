import pendulum
from pydantic import BaseModel, Field


class SystemInfoModel(BaseModel):
    """Data model for system information.

    Attributes
    ----------
        created_at (str): The time when the system information was created. e.g. "2021-01-01T00:00:00Z".
        updated_at (str): The time when the system information was updated. e.g. "2021-01-01T00:00:00Z".

    """

    created_at: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the system information was created",
    )
    updated_at: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the system information was updated",
    )

    def update_time(self) -> None:
        """Update the time when the system information was updated."""
        self.updated_at = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
