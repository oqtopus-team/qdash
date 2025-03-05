from datetime import datetime

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class ExecutionRunModel(Document):
    date: str
    index: int
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "execution_run"
        indexes = [IndexModel([("date", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )
