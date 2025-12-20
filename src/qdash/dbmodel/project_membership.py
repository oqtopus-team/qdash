from __future__ import annotations

from typing import ClassVar, cast

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel


class ProjectMembershipDocument(Document):
    """Represents a user's membership state in a project."""

    project_id: str = Field(..., description="Project identifier")
    username: str = Field(..., description="Member username")
    role: ProjectRole = Field(default=ProjectRole.VIEWER, description="Assigned project role")
    status: str = Field(default="pending", description="Invitation status")
    invited_by: str | None = Field(default=None, description="Inviter username")
    last_accessed_at: str | None = Field(default=None, description="Last access timestamp ISO8601")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System info timestamps"
    )

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "project_membership"
        indexes: ClassVar = [
            IndexModel([("project_id", ASCENDING), ("username", ASCENDING)], unique=True),
            IndexModel([("username", ASCENDING), ("status", ASCENDING)]),
        ]

    @classmethod
    def get_active_membership(
        cls, project_id: str, username: str
    ) -> ProjectMembershipDocument | None:
        """Fetch active membership for the user/project pair."""
        result = cls.find_one(
            {"project_id": project_id, "username": username, "status": "active"}
        ).run()
        return cast("ProjectMembershipDocument | None", result)
