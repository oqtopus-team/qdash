from datetime import datetime

from bunnet import Document, Granularity, TimeSeriesConfig
from pydantic import BaseModel, ConfigDict

from .system_info import SystemInfo


class BaseFridgeSchema(BaseModel):
    device_id: str
    timestamp: datetime
    data: dict

    system_info: SystemInfo


class FridgeDocument(Document):
    device_id: str
    timestamp: datetime
    data: dict

    system_info: SystemInfo
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "fridge"

        timeseries = TimeSeriesConfig(
            time_field="timestamp",  #  Required
            meta_field="metadata",  #  Optional
            granularity=Granularity.hours,  #  Optional
            expire_after_seconds=604800 * 4,  #  Optional
        )

    @classmethod
    def from_domain(cls, domain: BaseFridgeSchema) -> "FridgeDocument":
        return cls(
            **domain.model_dump(),
        )

    def to_domain(self) -> BaseFridgeSchema:
        return BaseFridgeSchema(**self.model_dump())
