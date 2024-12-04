from bunnet import Document
from pydantic import ConfigDict
from pymongo import ASCENDING, IndexModel


class CoolingDownModel(Document):
    cooling_down_id: int
    date: str
    qpu_name: str
    size: int

    class Settings:
        name = "cooling_down"
        indexes = [IndexModel([("date", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_latest_cooling_down_id(cls):
        return cls.find_one(sort=[("cooling_down_id", -1)]).run().cooling_down_id
