"""Admin schemas for user and project management."""

from datetime import datetime

from pydantic import BaseModel, Field

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.user import SystemRole, Username


class UserListItem(BaseModel):
    """User summary for admin list view."""

    user_id: str
    username: str
    display_name: str | None = None
    organization: str | None = None
    avatar_key: str | None = None
    disabled: bool = False
    system_role: SystemRole = SystemRole.USER
    default_project_id: str | None = None
    must_change_password: bool = False


class ProjectListItem(BaseModel):
    """Project summary for admin list view."""

    project_id: str
    name: str
    owner_user_id: str
    owner_username: str
    description: str | None = None
    member_count: int = 0
    created_at: datetime | None = None


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

    display_name: str | None = None
    organization: str | None = None
    avatar_key: str | None = None
    disabled: bool | None = None
    system_role: SystemRole | None = None


class UserDetailResponse(BaseModel):
    """Detailed user response for admin view."""

    user_id: str
    username: str
    display_name: str | None = None
    organization: str | None = None
    avatar_key: str | None = None
    disabled: bool = False
    system_role: SystemRole = SystemRole.USER
    default_project_id: str | None = None
    must_change_password: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConfigReloadResponse(BaseModel):
    """Response model for config cache reload."""

    cleared: list[str] = Field(default_factory=list)


class SystemSettingsResponse(BaseModel):
    """System-wide runtime settings visible to administrators."""

    slack_forum_notifications_enabled: bool = False
    slack_webhook_configured: bool = False


class UpdateSystemSettingsRequest(BaseModel):
    """Request to update system-wide runtime settings."""

    slack_forum_notifications_enabled: bool


# --- Member Management ---


class MemberItem(BaseModel):
    """Member info for admin view."""

    user_id: str
    username: str
    display_name: str | None = None
    organization: str | None = None
    avatar_key: str | None = None
    role: ProjectRole
    status: str = "active"


class MemberListResponse(BaseModel):
    """Response containing list of project members."""

    members: list[MemberItem]
    total: int


class AddMemberRequest(BaseModel):
    """Request to add a member to a project."""

    username: Username
    role: ProjectRole = ProjectRole.VIEWER


# --- Bulk User Import ---


class BulkUserImportResult(BaseModel):
    """Result for a single row in a bulk user import."""

    row_number: int
    username: str
    display_name: str | None = None
    organization: str | None = None
    system_role: SystemRole = SystemRole.USER
    initial_password: str | None = None
    status: str
    message: str | None = None


class BulkUserImportResponse(BaseModel):
    """Response for bulk user import."""

    results: list[BulkUserImportResult]
    created: int
    skipped: int
    failed: int
    total: int
