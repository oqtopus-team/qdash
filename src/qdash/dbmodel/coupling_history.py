from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.common.datetime_utils import now
from qdash.datamodel.coupling import CouplingModel, EdgeInfoModel
from qdash.datamodel.system_info import SystemInfoModel


class CouplingHistoryDocument(Document):
    """Data model for coupling history.

    Attributes
    ----------
        project_id (str): The owning project identifier.
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling.
        status (str): The status of the coupling.
        edge_info (EdgeInfoModel): The edge information.
        system_info (SystemInfo): The system information.
        recorded_date (str): The date when this history record was created (YYYYMMDD).

    """

    project_id: str = Field(..., description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the coupling")
    qid: str = Field(..., description="The coupling ID")
    status: str = Field(..., description="The status of the coupling")
    chip_id: str = Field(..., description="The chip ID")
    data: dict[str, Any] = Field(..., description="The data of the coupling")
    best_data: dict[str, Any] = Field(
        default_factory=dict,
        description="The best calibration results, focusing on fidelity metrics",
    )
    edge_info: EdgeInfoModel | None = Field(
        default=None, description="The edge information (deprecated)"
    )
    system_info: SystemInfoModel = Field(..., description="The system information")
    recorded_date: str = Field(
        default_factory=lambda: now().strftime("%Y%m%d"),
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
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("qid", ASCENDING),
                    ("username", ASCENDING),
                    ("recorded_date", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("recorded_date", DESCENDING)]
            ),
        ]

    @classmethod
    def create_history(cls, coupling: CouplingModel) -> "CouplingHistoryDocument":
        """Create a history record from a CouplingDocument."""
        today = now().strftime("%Y%m%d")
        existing_history = cls.find_one(
            {
                "project_id": coupling.project_id,
                "chip_id": coupling.chip_id,
                "qid": coupling.qid,
                "username": coupling.username,
                "recorded_date": today,
            }
        ).run()
        if existing_history:
            history = existing_history
            history.data = coupling.data
            history.best_data = coupling.best_data
            history.status = coupling.status
            history.edge_info = coupling.edge_info
        else:
            history = cls(
                project_id=coupling.project_id,
                username=coupling.username,
                qid=coupling.qid,
                status=coupling.status,
                chip_id=coupling.chip_id,
                data=coupling.data,
                best_data=coupling.best_data,
                edge_info=coupling.edge_info,
                system_info=SystemInfoModel(),
            )
        history.save()
        return history
