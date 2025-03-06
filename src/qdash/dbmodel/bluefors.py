from datetime import datetime
from typing import Optional

from bunnet import Document, Granularity, TimeSeriesConfig
from pydantic import ConfigDict, Field
from pymongo import IndexModel


class BlueforsModel(Document):
    id: str
    device_id: str
    timestamp: datetime
    resistance: float
    reactance: float
    temperature: float
    rez: float
    imz: float
    magnitude: float
    angle: float
    channel_nr: int
    status_flags: int | None = Field(None)
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "bluefors"
        # collection.create_index("_id")
        # collection.create_index("channel_nr")
        indexes = [IndexModel(["channel_nr"])]

        timeseries = TimeSeriesConfig(
            time_field="timestamp",  #  Required
            meta_field="metadata",  #  Optional
            granularity=Granularity.hours,  #  Optional
            expire_after_seconds=604800 * 4,  #  Optional
        )
