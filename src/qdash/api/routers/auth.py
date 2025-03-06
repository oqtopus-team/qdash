from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.logger import logger
from qdash.api.lib.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_active_user,
    get_password_hash,
)
from qdash.api.schemas.auth import Token, User, UserCreate
from qdash.datamodel.system_info import SystemInfoModel
from qdash.neodbmodel.initialize import initialize
from qdash.neodbmodel.user import UserDocument

initialize()

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/token",
    response_model=Token,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "username": {"type": "string"},
                            "password": {"type": "string"},
                            "grant_type": {"type": "string", "default": "password"},
                        },
                        "required": ["username", "password"],
                    }
                }
            }
        }
    },
)
def login_for_access_token(
    username: str = Form(),
    password: str = Form(),
    grant_type: str = Form(default="password"),
) -> Token:
    logger.debug(f"Login attempt for user: {username}")
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    logger.debug(f"Access token created for user: {user.username}")
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=User)
def register_user(user_data: UserCreate) -> User:
    logger.debug(f"Registration attempt for user: {user_data.username}")
    # Check if username already exists
    initialize()
    query = UserDocument.find_one({"username": user_data.username}).run()
    existing_user = query
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = UserDocument(
        username=user_data.username,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        system_info=SystemInfoModel(),
    )
    user.insert()
    logger.debug(f"New user created: {user_data.username}")

    return User(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled,
    )


@router.get("/me", response_model=User)
def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    logger.debug(f"Reading user info for: {current_user.username}")
    return current_user


@router.post("/logout")
def logout():
    """Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the token is managed client-side.
    The client will remove the token from cookies.
    """
    return {"message": "Successfully logged out"}
