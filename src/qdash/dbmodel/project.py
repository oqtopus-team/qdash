from __future__ import annotations

import uuid
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel


class ProjectDocument(Document):
    """Mongo document representing a collaborative project."""

    project_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Project identifier")
    owner_username: str = Field(..., description="Project owner username")
    name: str = Field(..., description="Project display name")
    description: str | None = Field(default=None, description="Project description")
    tags: list[str] = Field(default_factory=list, description="Project tags")
    default_role: ProjectRole = Field(default=ProjectRole.VIEWER, description="Default role for invite links")
    system_info: SystemInfoModel = Field(default_factory=SystemInfoModel, description="System info timestamps")

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo collection metadata."""

        name = "project"
        indexes: ClassVar = [
            IndexModel([("project_id", ASCENDING)], unique=True),
            IndexModel([("owner_username", ASCENDING), ("name", ASCENDING)], unique=True),
        ]

    @classmethod
    def find_by_id(cls, project_id: str) -> ProjectDocument | None:
        """Helper to lookup project by id."""
        return cls.find_one({"project_id": project_id}).run()
