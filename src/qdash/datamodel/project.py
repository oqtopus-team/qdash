from enum import Enum

from pydantic import BaseModel, Field
from qdash.datamodel.system_info import SystemInfoModel


class ProjectRole(str, Enum):
    """Role of a member inside a project.

    Simplified model:
    - OWNER: Full access to project (read, write, admin)
    - VIEWER: Read-only access (for invited members)
    """

    OWNER = "owner"
    VIEWER = "viewer"


class ProjectModel(BaseModel):
    """Represents a collaborative project/workspace."""

    project_id: str = Field(..., description="Globally unique project identifier")
    owner_username: str = Field(..., description="Username of the project owner")
    name: str = Field(..., description="Display name of the project")
    description: str | None = Field(default=None, description="Project description")
    tags: list[str] = Field(default_factory=list, description="Optional project labels")
    system_info: SystemInfoModel = Field(default_factory=SystemInfoModel)


class ProjectMembershipModel(BaseModel):
    """Represents membership information of a project."""

    project_id: str = Field(..., description="Project identifier")
    username: str = Field(..., description="Member username")
    role: ProjectRole = Field(
        default=ProjectRole.VIEWER, description="Member role within the project"
    )
    invited_by: str | None = Field(default=None, description="User who invited this member")
    status: str = Field(default="pending", description="Invitation status")
    system_info: SystemInfoModel = Field(default_factory=SystemInfoModel)
