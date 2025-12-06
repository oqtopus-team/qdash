"""Authentication router for QDash API."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.logger import logger
from qdash.api.lib.auth import (
    authenticate_user,
    get_current_active_user,
    get_password_hash,
)
from qdash.api.lib.project_service import ProjectService
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
    """Authenticate user and return access token.

    Validates user credentials against the database and returns an access token
    for subsequent authenticated requests.

    Parameters
    ----------
    username : str
        User's username provided via form data
    password : str
        User's password provided via form data

    Returns
    -------
    TokenResponse
        Response containing access_token, token_type, and username

    Raises
    ------
    HTTPException
        401 if authentication fails due to incorrect username or password

    """
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
        default_project_id=user.default_project_id,
    )


@router.post("/register", response_model=UserWithToken, summary="Register a new user", operation_id="registerUser")
def register_user(user_data: UserCreate) -> UserWithToken:
    """Register a new user account.

    Creates a new user in the database with hashed password and generates
    an access token for immediate use.

    Parameters
    ----------
    user_data : UserCreate
        User registration data including username, password, and optional full_name

    Returns
    -------
    UserWithToken
        Newly created user information including access_token

    Raises
    ------
    HTTPException
        400 if the username is already registered

    """
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
    ProjectService().ensure_default_project(user)
    logger.debug(f"New user created: {user_data.username}")

    return UserWithToken(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled,
        default_project_id=user.default_project_id,
        access_token=user.access_token,
    )


@router.get("/me", response_model=User, summary="Get current user", operation_id="getCurrentUser")
def get_current_user(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    """Get current authenticated user information.

    Returns the profile information of the currently authenticated user
    based on the provided access token.

    Parameters
    ----------
    current_user : User
        Current authenticated user injected via dependency

    Returns
    -------
    User
        Current user's profile information including username, full_name,
        and disabled status

    """
    logger.debug(f"Reading user info for: {current_user.username}")
    return current_user


@router.post("/logout", summary="Logout user", operation_id="logout")
def logout() -> dict[str, str]:
    """Logout the current user.

    This endpoint serves as a logout confirmation. Since authentication tokens
    are managed client-side (via cookies), no server-side session invalidation
    is required. The client is responsible for removing the stored credentials.

    Returns
    -------
    dict[str, str]
        Success message confirming logout

    """
    return {"message": "Successfully logged out"}
