"""Custom dashboard document."""

from typing import ClassVar
from uuid import uuid4

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.datamodel.custom_dashboard import DashboardPanelModel, DashboardVisibility
from qdash.datamodel.system_info import SystemInfoModel


def _new_dashboard_id() -> str:
    return f"dash_{uuid4().hex[:12]}"


class CustomDashboardDocument(Document):
    """A dashboard composed of panels by a project member."""

    project_id: str = Field(..., description="Owning project identifier")
    dashboard_id: str = Field(
        default_factory=_new_dashboard_id, description="Project-unique dashboard identifier"
    )
    user_id: str | None = Field(default=None, description="Owner user ID")
    username: str = Field(..., description="Owner username snapshot")
    name: str = Field(..., description="Display name")
    description: str = Field(default="", description="Free-form description")
    visibility: DashboardVisibility = Field(
        default="private",
        description="'private' (owner only) or 'project' (all project members)",
    )
    chip_id: str | None = Field(default=None, description="Default chip the panels read")
    panels: list[DashboardPanelModel] = Field(default_factory=list, description="Panels")
    version: int = Field(default=0, description="Write counter; incremented by every save")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="Created/updated timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "custom_dashboard"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("dashboard_id", ASCENDING)],
                unique=True,
                name="project_dashboard_unique",
            ),
            IndexModel([("project_id", ASCENDING), ("visibility", ASCENDING)]),
            IndexModel([("project_id", ASCENDING), ("user_id", ASCENDING)]),
        ]

    model_config = ConfigDict(from_attributes=True)
