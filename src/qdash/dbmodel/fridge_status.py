from typing import Optional

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import IndexModel


class ChannelInfo(BaseModel):
    status: str = "normal"  # normal, abnormal
    threshold: float | None = Field(None)

    model_config = ConfigDict(
        from_attributes=True,
    )


class FridgeStatusModel(Document):
    device_id: str
    ch1: ChannelInfo | None = Field(None)
    ch2: ChannelInfo | None = Field(None)
    ch5: ChannelInfo | None = Field(None)
    ch6: ChannelInfo | None = Field(None)

    class Settings:
        name = "fridge_status"
        # collection.create_index("_id")
        # collection.create_index("channel_nr")
        indexes = [IndexModel(["device_id"], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )
