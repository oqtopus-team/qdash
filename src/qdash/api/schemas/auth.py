from pydantic import BaseModel


class User(BaseModel):
    """User model for authentication and user management."""

    username: str
    full_name: str | None = None
    disabled: bool | None = None


class UserWithToken(BaseModel):
    """User model with access token for login/register responses."""

    username: str
    full_name: str | None = None
    disabled: bool | None = None
    access_token: str


class UserInDB(User):
    """User model for database storage, including hashed password."""

    hashed_password: str
    access_token: str


class UserCreate(BaseModel):
    """User creation model for registration."""

    username: str
    password: str
    full_name: str | None = None


class TokenResponse(BaseModel):
    """Token response model for login."""

    access_token: str
    token_type: str = "bearer"
    username: str
