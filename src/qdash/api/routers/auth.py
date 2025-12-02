import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.logger import logger
from qdash.api.lib.auth import (
    authenticate_user,
    get_current_active_user,
    get_password_hash,
)
from qdash.api.schemas.auth import TokenResponse, User, UserCreate, UserWithToken
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument


def generate_access_token() -> str:
    """Generate a secure random access token."""
    return secrets.token_urlsafe(32)


router = APIRouter(
    prefix="/auth",
    responses={404: {"description": "Not found"}},
)


@router.post("/login", response_model=TokenResponse, summary="Login user", operation_id="login")
def login(
    username: str = Form(),
    password: str = Form(),
) -> TokenResponse:
    """Login endpoint to authenticate user and return access token."""
    logger.debug(f"Login attempt for user: {username}")
    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.debug(f"Login successful for user: {user.username}")
    return TokenResponse(
        access_token=user.access_token,
        token_type="bearer",
        username=user.username,
    )


@router.post("/register", response_model=UserWithToken, summary="Register a new user", operation_id="registerUser")
def register_user(user_data: UserCreate) -> UserWithToken:
    """Register a new user and return access token."""
    logger.debug(f"Registration attempt for user: {user_data.username}")
    # Check if username already exists
    query = UserDocument.find_one({"username": user_data.username}).run()
    existing_user = query
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Create new user with access token
    hashed_password = get_password_hash(user_data.password)
    access_token = generate_access_token()
    user = UserDocument(
        username=user_data.username,
        hashed_password=hashed_password,
        access_token=access_token,
        full_name=user_data.full_name,
        system_info=SystemInfoModel(),
    )
    user.insert()
    logger.debug(f"New user created: {user_data.username}")

    return UserWithToken(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled,
        access_token=user.access_token,
    )


@router.get("/me", response_model=User, summary="Get current user", operation_id="getCurrentUser")
def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    """Get current user information."""
    logger.debug(f"Reading user info for: {current_user.username}")
    return current_user


@router.post("/logout", summary="Logout user", operation_id="logout")
def logout() -> dict[str, str]:
    """Logout endpoint.

    This endpoint doesn't need to do anything on the backend since the username is managed client-side.
    The client will remove the username from cookies.
    """
    return {"message": "Successfully logged out"}
