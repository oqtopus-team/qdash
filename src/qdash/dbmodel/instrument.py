from typing import Optional

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import IndexModel


class PortConfig(BaseModel):
    port: Optional[int] = Field(default=0)
    direction: Optional[str] = Field(default="")
    lo_freq: Optional[float] = Field(default=0)
    cnco_freq: Optional[float] = Field(default=0)
    fullscale_current: Optional[int] = Field(default=0)
    sideband: Optional[str] = Field(default="")


class InstrumentModel(Document):
    label: str
    name: str
    type: str
    status: str
    address: str
    adapter: str
    detail: Optional[list[PortConfig]] = None

    class Settings:
        name = "instrument"
        indexes = [IndexModel([("address", 1)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )
