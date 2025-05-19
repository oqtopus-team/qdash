from typing import ClassVar

import pendulum
from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.coupling import CouplingModel, EdgeInfoModel
from qdash.datamodel.system_info import SystemInfoModel


class CouplingHistoryDocument(Document):
    """Data model for coupling history.

    Attributes
    ----------
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling.
        status (str): The status of the coupling.
        edge_info (EdgeInfoModel): The edge information.
        system_info (SystemInfo): The system information.
        recorded_date (str): The date when this history record was created (YYYY-MM-DD).

    """

    username: str = Field(..., description="The username of the user who created the coupling")
    qid: str = Field(..., description="The coupling ID")
    status: str = Field(..., description="The status of the coupling")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the coupling")
    edge_info: EdgeInfoModel = Field(..., description="The edge information")
    system_info: SystemInfoModel = Field(..., description="The system information")
    recorded_date: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").format("YYYY-MM-DD"),
        description="The date when this history record was created",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "coupling_history"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("chip_id", ASCENDING),
                    ("qid", ASCENDING),
                    ("username", ASCENDING),
                    ("recorded_date", ASCENDING),
                ],
                unique=True,
            )
        ]

    @classmethod
    def create_history(cls, coupling: CouplingModel) -> "CouplingHistoryDocument":
        """Create a history record from a CouplingDocument."""
        today = pendulum.now(tz="Asia/Tokyo").format("YYYY-MM-DD")
        existing_history = cls.find_one(
            {
                "chip_id": coupling.chip_id,
                "qid": coupling.qid,
                "username": coupling.username,
                "recorded_date": today,
            }
        ).run()
        if existing_history:
            history = existing_history
            history.data = coupling.data
            history.status = coupling.status
            history.edge_info = coupling.edge_info
        else:
            history = cls(
                username=coupling.username,
                qid=coupling.qid,
                status=coupling.status,
                chip_id=coupling.chip_id,
                data=coupling.data,
                edge_info=coupling.edge_info,
            )
        history.save()
        return history
