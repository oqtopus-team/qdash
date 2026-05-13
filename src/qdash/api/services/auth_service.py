"""Service for authentication-related business operations."""

from __future__ import annotations

import logging
import os
import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from qdash.api.lib.auth import get_password_hash, get_user, verify_password
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole, generate_user_id
from qdash.dbmodel.user import UserDocument

if TYPE_CHECKING:
    from qdash.api.schemas.auth import PasswordChange, PasswordReset, UserCreate, UserProfileUpdate
    from qdash.api.services.project_service import ProjectService
    from qdash.repository import MongoUserRepository

logger = logging.getLogger(__name__)
TEMPORARY_PASSWORD_LENGTH = 18


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


def generate_temporary_password() -> str:
    """Generate a URL-safe temporary password for new users."""
    # token_urlsafe may return a little more than requested; trim to keep UI compact.
    return secrets.token_urlsafe(24)[:TEMPORARY_PASSWORD_LENGTH]


class AuthService:
    """Service for user registration and password management.

    Authentication infrastructure (authenticate_user, get_current_active_user)
    remains in lib/auth.py. This service handles business operations like
    registration and password changes.
    """

    def __init__(
        self,
        user_repository: MongoUserRepository,
        project_service: ProjectService | None = None,
    ) -> None:
        """Initialize the service with repositories."""
        self._user_repo = user_repository
        self._project_service = project_service

    def register_user(
        self,
        user_data: UserCreate,
        admin_username: str,
    ) -> tuple[UserDocument, str, str | None]:
        """Register a new user account.

        Parameters
        ----------
        user_data : UserCreate
            User registration data.
        admin_username : str
            Username of the admin performing the registration.

        Returns
        -------
        tuple[UserDocument, str, str | None]
            The created user document, access token, and generated password if any.

        Raises
        ------
        HTTPException
            400 if the username is already registered.

        """
        logger.debug(f"Admin {admin_username} creating user: {user_data.username}")

        existing_user = self._user_repo.find_by_username(user_data.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered",
            )

        initial_password: str | None = None
        password = user_data.password
        if password is None:
            initial_password = generate_temporary_password()
            password = initial_password

        hashed_password = get_password_hash(password)
        access_token = secrets.token_urlsafe(32)
        system_role = _get_system_role_for_user(user_data.username)

        user = UserDocument(
            user_id=generate_user_id(),
            username=user_data.username,
            hashed_password=hashed_password,
            access_token=access_token,
            display_name=user_data.display_name,
            organization=user_data.organization,
            avatar_key=user_data.avatar_key,
            system_role=system_role,
            must_change_password=True,
            system_info=SystemInfoModel(),
        )
        self._user_repo.insert(user)
        logger.info(f"Admin {admin_username} created new user: {user_data.username}")

        return user, access_token, initial_password

    def onboard_user(self, user: UserDocument) -> None:
        """Create a default project for a newly registered user.

        Parameters
        ----------
        user : UserDocument
            The newly created user document.

        Raises
        ------
        RuntimeError
            If project_service was not injected.

        """
        if self._project_service is None:
            raise RuntimeError("ProjectService is required for onboarding")

        project = self._project_service.create_project(
            owner_username=user.username,
            name=f"{user.username}'s project",
        )
        self._project_service.set_user_default_project(user, project.project_id)
        logger.info(f"Created default project for user: {user.username}")

    def change_password(
        self,
        username: str,
        password_data: PasswordChange,
    ) -> dict[str, str]:
        """Change a user's password.

        Parameters
        ----------
        username : str
            The username of the user changing their password.
        password_data : PasswordChange
            Contains current_password and new_password.

        Returns
        -------
        dict[str, str]
            Success message.

        Raises
        ------
        HTTPException
            400 if current password is incorrect or new password is empty.
            404 if user not found.

        """
        logger.debug(f"Password change attempt for user: {username}")

        user_in_db = get_user(username)
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

        if not password_data.new_password or len(password_data.new_password) < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password cannot be empty",
            )

        new_hashed_password = get_password_hash(password_data.new_password)
        user_doc = self._user_repo.find_by_username(username)
        if user_doc:
            user_doc.hashed_password = new_hashed_password
            user_doc.must_change_password = False
            self._user_repo.save(user_doc)
            logger.info(f"Password changed successfully for user: {username}")
            return {"message": "Password changed successfully"}

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password",
        )

    def update_profile(
        self,
        username: str,
        profile_data: UserProfileUpdate,
    ) -> UserDocument:
        """Update profile fields owned by the current user."""
        user_doc = self._user_repo.find_by_username(username)
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if "display_name" in profile_data.model_fields_set:
            user_doc.display_name = (profile_data.display_name or "").strip() or None
        if "avatar_key" in profile_data.model_fields_set:
            user_doc.avatar_key = (profile_data.avatar_key or "").strip() or None
        self._user_repo.save(user_doc)
        return user_doc

    def reset_password(
        self,
        admin_username: str,
        password_data: PasswordReset,
    ) -> dict[str, str]:
        """Reset a user's password (admin operation).

        Parameters
        ----------
        admin_username : str
            Username of the admin performing the reset.
        password_data : PasswordReset
            Contains username and new_password.

        Returns
        -------
        dict[str, str]
            Success message.

        Raises
        ------
        HTTPException
            404 if target user not found.
            400 if new password is empty.

        """
        logger.debug(
            f"Admin {admin_username} attempting to reset password for: {password_data.username}"
        )

        user_doc = self._user_repo.find_by_username(password_data.username)
        if not user_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{password_data.username}' not found",
            )

        if not password_data.new_password or len(password_data.new_password) < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password cannot be empty",
            )

        new_hashed_password = get_password_hash(password_data.new_password)
        user_doc.hashed_password = new_hashed_password
        user_doc.must_change_password = True
        self._user_repo.save(user_doc)
        logger.info(f"Admin {admin_username} reset password for user: {password_data.username}")
        return {"message": f"Password reset successfully for user '{password_data.username}'"}
