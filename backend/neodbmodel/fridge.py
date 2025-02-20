from datetime import datetime

from bunnet import Document, Granularity, TimeSeriesConfig
from datamodel.fridge import FridgeModel
from datamodel.system_info import SystemInfoModel
from pydantic import ConfigDict, Field


class FridgeDocument(Document):
    """Document for a fridge.

    Attributes
    ----------
        device_id (str): The device ID.
        timestamp (datetime): The timestamp.
        data (dict): The data.
        system_info (SystemInfo): The system information.

    """

    device_id: str = Field(..., description="The device ID")
    timestamp: datetime = Field(..., description="The timestamp")
    data: dict = Field(..., description="The data")

    system_info: SystemInfoModel = Field(..., description="The system information")
    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "fridge"

        timeseries = TimeSeriesConfig(
            time_field="timestamp",  #  Required
            meta_field="metadata",  #  Optional
            granularity=Granularity.hours,  #  Optional
            expire_after_seconds=604800 * 4,  #  Optional
        )

    @classmethod
    def from_domain(cls, domain: FridgeModel) -> "FridgeDocument":
        return cls(
            **domain.model_dump(),
        )

    def to_domain(self) -> FridgeModel:
        return FridgeModel(**self.model_dump())
