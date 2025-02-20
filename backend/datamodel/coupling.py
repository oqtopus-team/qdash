from datamodel.system_info import SystemInfoModel
from pydantic import BaseModel, Field


class CouplingModel(BaseModel):
    """Data model for a coupling.

    Attributes
    ----------
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling. e.g. {"coupling_strength": 0.1}.
        calibrated_at (str): The time when the coupling was calibrated. e.g. "2021-01-01T00:00:00Z".
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    qid: str = Field(..., description="The coupling ID")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the coupling")
    calibrated_at: str = Field(..., description="The time when the coupling was calibrated")

    system_info: SystemInfoModel = Field(..., description="The system information")


class EdgeInfoModel(BaseModel):
    """Data model for an edge information.

    Attributes
    ----------
        fill (str): The fill color.
        position (PositionModel): The position.

    """

    fill: str = Field(..., description="The fill color")
