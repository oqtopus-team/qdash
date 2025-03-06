from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.coupling import EdgeInfoModel
from qdash.datamodel.system_info import SystemInfoModel


class CouplingDocument(Document):
    """Coupling document.

    Attributes
    ----------
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling. e.g. {"coupling_strength": 0.1}.
        calibrated_at (str): The time when the coupling was calibrated. e.g. "2021-01-01T00:00:00Z".
        edge_info (EdgeInfoModel): The edge information. e.g. {"fill": "red", "position": {"x": 0.0, "y": 0.0}}.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    username: str = Field(..., description="The username of the user who created the coupling")
    qid: str = Field(..., description="The coupling ID")
    status: str = Field("pending", description="The status of the coupling")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the coupling")
    edge_info: EdgeInfoModel = Field(..., description="The edge information")

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "coupling"
        indexes: ClassVar = [IndexModel([("chip_id", ASCENDING), ("qid", ASCENDING)], unique=True)]
