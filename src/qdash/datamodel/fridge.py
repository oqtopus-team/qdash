from datetime import datetime

from pydantic import BaseModel, Field
from qdash.datamodel.system_info import SystemInfoModel


class FridgeModel(BaseModel):
    """Data model for a fridge.

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
