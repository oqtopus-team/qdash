from datetime import datetime

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class ExperimentModel(Document):
    experiment_name: str
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "experiment"
        indexes = [IndexModel([("experiment_name", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )
