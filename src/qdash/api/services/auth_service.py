"""Service for authentication-related business operations."""

from __future__ import annotations

import logging
import os
import secrets
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from qdash.api.lib.auth import get_password_hash, get_user, verify_password
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.user import UserDocument

if TYPE_CHECKING:
    from qdash.api.schemas.auth import PasswordChange, PasswordReset, UserCreate
    from qdash.api.services.project_service import ProjectService
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
    ) -> tuple[UserDocument, str]:
        """Register a new user account.

        Parameters
        ----------
        user_data : UserCreate
            User registration data.
        admin_username : str
            Username of the admin performing the registration.

        Returns
        -------
        tuple[UserDocument, str]
            The created user document and access token.

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

        hashed_password = get_password_hash(user_data.password)
        access_token = secrets.token_urlsafe(32)
        system_role = _get_system_role_for_user(user_data.username)

        user = UserDocument(
            username=user_data.username,
            hashed_password=hashed_password,
            access_token=access_token,
            full_name=user_data.full_name,
            system_role=system_role,
            system_info=SystemInfoModel(),
        )
        self._user_repo.insert(user)
        logger.info(f"Admin {admin_username} created new user: {user_data.username}")

        return user, access_token

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
            self._user_repo.save(user_doc)
            logger.info(f"Password changed successfully for user: {username}")
            return {"message": "Password changed successfully"}

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password",
        )

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
        self._user_repo.save(user_doc)
        logger.info(f"Admin {admin_username} reset password for user: {password_data.username}")
        return {"message": f"Password reset successfully for user '{password_data.username}'"}
