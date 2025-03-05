from typing import Optional

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import IndexModel


class Wiring(BaseModel):
    control: dict[str, dict[str, str]]
    readout: dict[str, dict[str, str]]
    bias: Optional[dict[str, dict[str, str]]] = Field(default=None, exclude=True)
    pump: Optional[dict[str, dict[str, str]]] = Field(default=None, exclude=True)


class WiringInfoModel(Document):
    name: str
    wiring_dict: Wiring
    active: bool
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "wiring_info"
        indexes = [IndexModel([("name", 1)], unique=True)]

    @classmethod
    def get_active_wiring(cls):
        return cls.find_one(cls.active == True).run()

    @classmethod
    def get_active_wiring_dict(cls):
        return cls.get_active_wiring().wiring_dict.dict()

    @classmethod
    def get_active_wiring_name(cls):
        return cls.get_active_wiring().name
