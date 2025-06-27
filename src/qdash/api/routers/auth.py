from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.logger import logger
from qdash.api.lib.auth import (
    authenticate_user,
    get_current_active_user,
    get_password_hash,
)
from qdash.api.schemas.auth import User, UserCreate
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={404: {"description": "Not found"}},
)


@router.post("/login")
def login(
    username: str = Form(),
    password: str = Form(),
) -> dict[str, str]:
    """Login endpoint to authenticate user and return username."""
    logger.debug(f"Login attempt for user: {username}")
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    logger.debug(f"Login successful for user: {user.username}")
    return {"username": user.username}


@router.post("/register", response_model=User)
def register_user(user_data: UserCreate) -> User:
    """Register a new user."""
    logger.debug(f"Registration attempt for user: {user_data.username}")
    # Check if username already exists
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
    """Get current user information."""
    logger.debug(f"Reading user info for: {current_user.username}")
    return current_user


@router.post("/logout")
def logout() -> dict[str, str]:
    """Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the username is managed client-side.
    The client will remove the username from cookies.
    """
    return {"message": "Successfully logged out"}
