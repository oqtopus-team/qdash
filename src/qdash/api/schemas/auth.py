from pydantic import BaseModel, Field
from qdash.datamodel.user import SystemRole, Username


class User(BaseModel):
    """User model for authentication and user management."""

    user_id: str
    username: str
    display_name: str | None = None
    organization: str | None = None
    avatar_key: str | None = None
    disabled: bool | None = None
    default_project_id: str | None = None
    must_change_password: bool = False
    system_role: SystemRole = SystemRole.USER


class UserWithToken(BaseModel):
    """User model with access token for login/register responses."""

    user_id: str
    username: str
    display_name: str | None = None
    organization: str | None = None
    avatar_key: str | None = None
    disabled: bool | None = None
    default_project_id: str | None = None
    must_change_password: bool = False
    system_role: SystemRole = SystemRole.USER
    access_token: str
    initial_password: str | None = None


class UserInDB(User):
    """User model for database storage, including hashed password."""

    hashed_password: str
    access_token: str


class UserCreate(BaseModel):
    """User creation model for registration (admin only)."""

    username: Username
    password: str | None = None
    display_name: str | None = None
    organization: str | None = None
    avatar_key: str | None = None
    create_default_project: bool = False


class UserProfileUpdate(BaseModel):
    """Current user profile update model."""

    display_name: str | None = Field(default=None, max_length=100)
    avatar_key: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9_-]+$")


class TokenResponse(BaseModel):
    """Token response model for login."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    default_project_id: str | None = None
    must_change_password: bool = False


class PasswordChange(BaseModel):
    """Password change request model."""

    current_password: str
    new_password: str


class PasswordReset(BaseModel):
    """Password reset request model (admin only)."""

    username: Username
    new_password: str
