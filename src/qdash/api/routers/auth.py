"""Authentication router for QDash API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from qdash.api.dependencies import get_auth_service
from qdash.api.lib.auth import authenticate_user, get_current_active_user
from qdash.api.schemas.auth import (
    PasswordChange,
    PasswordReset,
    TokenResponse,
    User,
    UserCreate,
    UserProfileUpdate,
    UserWithToken,
)
from qdash.api.services.auth_service import AuthService
from qdash.datamodel.user import SystemRole

logger = logging.getLogger(__name__)

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
        user_id=user.user_id,
        username=user.username,
        default_project_id=user.default_project_id,
        must_change_password=user.must_change_password,
    )


@router.post(
    "/register",
    response_model=UserWithToken,
    summary="Register a new user (admin only)",
    operation_id="registerUser",
)
def register_user(
    user_data: UserCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserWithToken:
    """Register a new user account (admin only).

    Parameters
    ----------
    user_data : UserCreate
        User registration data including username, password, and optional display_name
    current_user : User
        Current authenticated admin user
    auth_service : AuthService
        The auth service instance

    Returns
    -------
    UserWithToken
        Newly created user information including access_token

    Raises
    ------
    HTTPException
        403 if the current user is not an admin
        400 if the username is already registered

    """
    if current_user.system_role != SystemRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create new users",
        )

    user, _access_token, initial_password = auth_service.register_user(
        user_data, current_user.username
    )
    if user_data.create_default_project:
        auth_service.onboard_user(user)

    return UserWithToken(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        organization=user.organization,
        avatar_key=user.avatar_key,
        disabled=user.disabled,
        default_project_id=user.default_project_id,
        must_change_password=user.must_change_password,
        access_token=user.access_token,
        initial_password=initial_password,
    )


@router.get("/me", response_model=User, summary="Get current user", operation_id="getCurrentUser")
def get_current_user(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    """Get current authenticated user information.

    Parameters
    ----------
    current_user : User
        Current authenticated user injected via dependency

    Returns
    -------
    User
        Current user's profile information

    """
    logger.debug(f"Reading user info for: {current_user.username}")
    return current_user


@router.patch(
    "/me",
    response_model=User,
    summary="Update current user profile",
    operation_id="updateCurrentUserProfile",
)
def update_current_user_profile(
    profile_data: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """Update the current user's editable profile fields."""
    user = auth_service.update_profile(current_user.username, profile_data)
    return User(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        organization=user.organization,
        avatar_key=user.avatar_key,
        disabled=user.disabled,
        default_project_id=user.default_project_id,
        must_change_password=user.must_change_password,
        system_role=user.system_role,
    )


@router.post("/logout", summary="Logout user", operation_id="logout")
def logout() -> dict[str, str]:
    """Logout the current user.

    Returns
    -------
    dict[str, str]
        Success message confirming logout

    """
    return {"message": "Successfully logged out"}


@router.post(
    "/change-password",
    response_model=dict[str, str],
    summary="Change user password",
    operation_id="changePassword",
)
def change_password(
    password_data: PasswordChange,
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    """Change the current user's password.

    Parameters
    ----------
    password_data : PasswordChange
        Contains current_password and new_password
    current_user : User
        Current authenticated user injected via dependency
    auth_service : AuthService
        The auth service instance

    Returns
    -------
    dict[str, str]
        Success message confirming password change

    """
    return auth_service.change_password(current_user.username, password_data)


@router.post(
    "/reset-password",
    response_model=dict[str, str],
    summary="Reset user password (admin only)",
    operation_id="resetPassword",
)
def reset_password(
    password_data: PasswordReset,
    current_user: Annotated[User, Depends(get_current_active_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> dict[str, str]:
    """Reset a user's password (admin only).

    Parameters
    ----------
    password_data : PasswordReset
        Contains username and new_password
    current_user : User
        Current authenticated admin user
    auth_service : AuthService
        The auth service instance

    Returns
    -------
    dict[str, str]
        Success message confirming password reset

    Raises
    ------
    HTTPException
        403 if the current user is not an admin

    """
    if current_user.system_role != SystemRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can reset user passwords",
        )

    return auth_service.reset_password(current_user.username, password_data)
