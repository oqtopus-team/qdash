"""Admin schemas for user and project management."""

from pydantic import BaseModel
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.user import SystemRole


class UserListItem(BaseModel):
    """User summary for admin list view."""

    username: str
    full_name: str | None = None
    disabled: bool = False
    system_role: SystemRole = SystemRole.USER
    default_project_id: str | None = None


class ProjectListItem(BaseModel):
    """Project summary for admin list view."""

    project_id: str
    name: str
    owner_username: str
    description: str | None = None
    member_count: int = 0
    created_at: str | None = None


class ProjectListResponse(BaseModel):
    """Response containing list of all projects."""

    projects: list[ProjectListItem]
    total: int


class UserListResponse(BaseModel):
    """Response containing list of users."""

    users: list[UserListItem]
    total: int


class UpdateUserRequest(BaseModel):
    """Request to update user settings (admin only)."""

    full_name: str | None = None
    disabled: bool | None = None
    system_role: SystemRole | None = None


class UserDetailResponse(BaseModel):
    """Detailed user response for admin view."""

    username: str
    full_name: str | None = None
    disabled: bool = False
    system_role: SystemRole = SystemRole.USER
    default_project_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# --- Member Management ---


class MemberItem(BaseModel):
    """Member info for admin view."""

    username: str
    full_name: str | None = None
    role: ProjectRole
    status: str = "active"


class MemberListResponse(BaseModel):
    """Response containing list of project members."""

    members: list[MemberItem]
    total: int


class AddMemberRequest(BaseModel):
    """Request to add a member to a project (always as viewer)."""

    username: str
