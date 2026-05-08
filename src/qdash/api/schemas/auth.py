from pydantic import BaseModel
from qdash.datamodel.user import SystemRole


class User(BaseModel):
    """User model for authentication and user management."""

    user_id: str
    username: str
    full_name: str | None = None
    disabled: bool | None = None
    default_project_id: str | None = None
    must_change_password: bool = False
    system_role: SystemRole = SystemRole.USER


class UserWithToken(BaseModel):
    """User model with access token for login/register responses."""

    user_id: str
    username: str
    full_name: str | None = None
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

    username: str
    password: str | None = None
    full_name: str | None = None
    create_default_project: bool = False


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

    username: str
    new_password: str
