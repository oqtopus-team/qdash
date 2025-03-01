from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    hashed_password: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str | None = None
