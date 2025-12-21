"""Schemas for project management API."""

from datetime import datetime

from pydantic import BaseModel, Field
from qdash.datamodel.project import ProjectRole


class ProjectCreate(BaseModel):
    """Request schema for creating a new project."""

    name: str = Field(..., min_length=1, max_length=100, description="Project display name")
    description: str | None = Field(None, max_length=500, description="Project description")
    tags: list[str] = Field(default_factory=list, description="Project tags")


class ProjectUpdate(BaseModel):
    """Request schema for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=100, description="Project display name")
    description: str | None = Field(None, max_length=500, description="Project description")
    tags: list[str] | None = Field(None, description="Project tags")
    default_role: ProjectRole | None = Field(None, description="Default role for new members")


class ProjectResponse(BaseModel):
    """Response schema for project information."""

    project_id: str
    owner_username: str
    name: str
    description: str | None
    tags: list[str]
    default_role: ProjectRole
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """Response schema for listing projects."""

    projects: list[ProjectResponse]
    total: int


class MemberInvite(BaseModel):
    """Request schema for inviting a member."""

    username: str = Field(..., description="Username to invite")
    role: ProjectRole = Field(default=ProjectRole.VIEWER, description="Role to assign")


class MemberUpdate(BaseModel):
    """Request schema for updating a member's role."""

    role: ProjectRole = Field(..., description="New role for the member")


class MemberResponse(BaseModel):
    """Response schema for project membership."""

    project_id: str
    username: str
    role: ProjectRole
    status: str
    invited_by: str | None
    last_accessed_at: datetime | None


class MemberListResponse(BaseModel):
    """Response schema for listing project members."""

    members: list[MemberResponse]
    total: int
