from pydantic import BaseModel, Field

from .system_info import SystemInfoModel


class QubitModel(BaseModel):
    """Data model for a qubit.

    Attributes:
        qid (str): The qubit ID. e.g. "0".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the qubit. e.g. {"qubit_frequency": 5.0}.
        calibrated_at (str): The time when the qubit was calibrated. e.g. "2021-01-01T00:00:00Z".
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.
    """

    qid: str = Field(..., description="The qubit ID")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the qubit")
    calibrated_at: str = Field(..., description="The time when the qubit was calibrated")

    system_info: SystemInfoModel = Field(..., description="The system information")


class PositionModel(BaseModel):
    """Data model for a position.

    Attributes:
        x (float): The x-coordinate.
        y (float): The y-coordinate.
    """

    x: float = Field(..., description="The x-coordinate")
    y: float = Field(..., description="The y-coordinate")


class NodeInfoModel(BaseModel):
    """Data model for a node information.

    Attributes:
        fill (str): The fill color.
        position (PositionModel): The position.
    """

    fill: str = Field(..., description="The fill color")
    position: PositionModel = Field(..., description="The position")
