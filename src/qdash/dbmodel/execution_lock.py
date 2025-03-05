from datetime import datetime

from bunnet import Document
from pydantic import ConfigDict, Field


class ExecutionLockModel(Document):
    lock: bool
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "execution_lock"

    model_config = ConfigDict(
        from_attributes=True,
    )
