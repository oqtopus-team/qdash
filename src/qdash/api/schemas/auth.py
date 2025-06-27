from pydantic import BaseModel


class User(BaseModel):
    """User model for authentication and user management."""

    username: str
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    """User model for database storage, including hashed password."""

    hashed_password: str


class UserCreate(BaseModel):
    """User creation model for registration."""

    username: str
    password: str
    full_name: str | None = None
