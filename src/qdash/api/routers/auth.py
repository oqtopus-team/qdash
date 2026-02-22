"""Authentication router for QDash API."""

import logging
import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from qdash.api.lib.auth import (
    authenticate_user,
    get_current_active_user,
    get_password_hash,
    get_user,
    verify_password,
)
from qdash.api.lib.project_service import ProjectService
from qdash.api.schemas.auth import (
    PasswordChange,
    PasswordReset,
    TokenResponse,
    User,
    UserCreate,
    UserWithToken,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.user import UserDocument
from qdash.repository import MongoUserRepository

logger = logging.getLogger(__name__)


def _get_system_role_for_user(username: str) -> SystemRole:
    """Determine system role for a user based on environment variable.

    Parameters
    ----------
    username : str
        Username to check

    Returns
    -------
    SystemRole
        ADMIN if username matches QDASH_ADMIN_USERNAME, otherwise USER

    """
    admin_username = os.getenv("QDASH_ADMIN_USERNAME", "").strip()
    if not admin_username:
        return SystemRole.USER

    if username == admin_username:
        logger.info(f"User '{username}' registered as admin (via QDASH_ADMIN_USERNAME)")
        return SystemRole.ADMIN

    return SystemRole.USER


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


@router.post(
    "/register",
    response_model=UserWithToken,
    summary="Register a new user (admin only)",
    operation_id="registerUser",
)
def register_user(
    user_data: UserCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserWithToken:
    """Register a new user account (admin only).

    Creates a new user in the database with hashed password and generates
    an access token for immediate use. Only admin users can create new accounts.

    Parameters
    ----------
    user_data : UserCreate
        User registration data including username, password, and optional full_name
    current_user : User
        Current authenticated admin user

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
    # Check if current user is admin
    if current_user.system_role != SystemRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create new users",
        )

    logger.debug(f"Admin {current_user.username} creating user: {user_data.username}")

    user_repo = MongoUserRepository()

    # Check if username already exists
    existing_user = user_repo.find_by_username(user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Create new user with access token
    hashed_password = get_password_hash(user_data.password)
    access_token = generate_access_token()
    system_role = _get_system_role_for_user(user_data.username)
    user = UserDocument(
        username=user_data.username,
        hashed_password=hashed_password,
        access_token=access_token,
        full_name=user_data.full_name,
        system_role=system_role,
        system_info=SystemInfoModel(),
    )
    user_repo.insert(user)
    logger.info(f"Admin {current_user.username} created new user: {user_data.username}")

    # Create default project for every user
    service = ProjectService()
    project = service.create_project(
        owner_username=user.username,
        name=f"{user.username}'s project",
    )
    user.default_project_id = project.project_id
    user_repo.save(user)
    logger.info(f"Created default project for user: {user.username}")

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


@router.post(
    "/change-password",
    response_model=dict[str, str],
    summary="Change user password",
    operation_id="changePassword",
)
def change_password(
    password_data: PasswordChange,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Change the current user's password.

    Validates the current password and updates to the new password.

    Parameters
    ----------
    password_data : PasswordChange
        Contains current_password and new_password
    current_user : User
        Current authenticated user injected via dependency

    Returns
    -------
    dict[str, str]
        Success message confirming password change

    Raises
    ------
    HTTPException
        400 if current password is incorrect
        400 if new password is empty

    """
    logger.debug(f"Password change attempt for user: {current_user.username}")

    # Verify current password
    user_in_db = get_user(current_user.username)
    if not user_in_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not verify_password(password_data.current_password, user_in_db.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Validate new password
    if not password_data.new_password or len(password_data.new_password) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password cannot be empty",
        )

    # Update password in database
    new_hashed_password = get_password_hash(password_data.new_password)
    user_repo = MongoUserRepository()
    user_doc = user_repo.find_by_username(current_user.username)
    if user_doc:
        user_doc.hashed_password = new_hashed_password
        user_repo.save(user_doc)
        logger.info(f"Password changed successfully for user: {current_user.username}")
        return {"message": "Password changed successfully"}

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to update password",
    )


@router.post(
    "/reset-password",
    response_model=dict[str, str],
    summary="Reset user password (admin only)",
    operation_id="resetPassword",
)
def reset_password(
    password_data: PasswordReset,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, str]:
    """Reset a user's password (admin only).

    Allows administrators to reset any user's password without knowing
    the current password. This is useful for password recovery scenarios.

    Parameters
    ----------
    password_data : PasswordReset
        Contains username and new_password
    current_user : User
        Current authenticated admin user

    Returns
    -------
    dict[str, str]
        Success message confirming password reset

    Raises
    ------
    HTTPException
        403 if the current user is not an admin
        404 if the target user is not found
        400 if new password is empty

    """
    # Check if current user is admin
    if current_user.system_role != SystemRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can reset user passwords",
        )

    logger.debug(
        f"Admin {current_user.username} attempting to reset password for: {password_data.username}"
    )

    user_repo = MongoUserRepository()

    # Find target user
    user_doc = user_repo.find_by_username(password_data.username)
    if not user_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{password_data.username}' not found",
        )

    # Validate new password
    if not password_data.new_password or len(password_data.new_password) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password cannot be empty",
        )

    # Update password in database
    new_hashed_password = get_password_hash(password_data.new_password)
    user_doc.hashed_password = new_hashed_password
    user_repo.save(user_doc)
    logger.info(f"Admin {current_user.username} reset password for user: {password_data.username}")
    return {"message": f"Password reset successfully for user '{password_data.username}'"}
