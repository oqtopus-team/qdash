from typing import ClassVar

import pendulum
from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.qubit import NodeInfoModel, QubitModel
from qdash.datamodel.system_info import SystemInfoModel


class QubitHistoryDocument(Document):
    """Data model for qubit history.

    Attributes
    ----------
        qid (str): The qubit ID. e.g. "0".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the qubit.
        status (str): The status of the qubit.
        node_info (NodeInfoModel): The node information.
        system_info (SystemInfo): The system information.
        recorded_date (str): The date when this history record was created (YYYY-MM-DD).

    """

    username: str = Field(..., description="The username of the user who created the qubit")
    qid: str = Field(..., description="The qubit ID")
    status: str = Field(..., description="The status of the qubit")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the qubit")
    node_info: NodeInfoModel = Field(..., description="The node information")
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

        name = "qubit_history"
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
    def create_history(cls, qubit: QubitModel) -> "QubitHistoryDocument":
        """Create a history record from a QubitDocument."""
        today = pendulum.now(tz="Asia/Tokyo").format("YYYY-MM-DD")
        existing_history = cls.find_one(
            {
                "chip_id": qubit.chip_id,
                "qid": qubit.qid,
                "username": qubit.username,
                "recorded_date": today,
            }
        ).run()
        if existing_history:
            history = existing_history
            history.data = qubit.data
            history.status = qubit.status
            history.node_info = qubit.node_info
        else:
            # Create a new history record
            history = cls(
                username=qubit.username,
                qid=qubit.qid,
                status=qubit.status,
                chip_id=qubit.chip_id,
                data=qubit.data,
                node_info=qubit.node_info,
                system_info=qubit.system_info,
            )
        history.save()
        return history
