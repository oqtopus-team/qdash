from datetime import datetime

from bunnet import Document
from pydantic import ConfigDict, Field


class QPUModel(Document):
    name: str
    size: int
    nodes: list[str]
    edges: list[str]
    active: bool = Field(default=False)
    installed_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "qpu"

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_active_qpu(cls):
        return cls.find_one(cls.active == True).run()

    @classmethod
    def get_active_qpu_name(cls):
        return cls.find_one(cls.active == True).run().name
