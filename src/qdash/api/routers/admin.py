"""Admin router for user and system management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from qdash.api.dependencies import get_admin_service
from qdash.api.lib.auth import get_admin_user
from qdash.api.lib.config_loader import ConfigLoader
from qdash.api.lib.copilot_config import clear_copilot_config_cache
from qdash.api.lib.metrics_config import clear_metrics_config_cache
from qdash.api.lib.policy_config import clear_policy_config_cache
from qdash.api.schemas.admin import (
    AddMemberRequest,
    ConfigReloadResponse,
    MemberItem,
    MemberListResponse,
    ProjectListResponse,
    UpdateUserRequest,
    UserDetailResponse,
    UserListResponse,
)
from qdash.api.schemas.auth import User
from qdash.api.services.admin_service import AdminService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    responses={404: {"description": "Not found"}},
)


@router.post(
    "/config/reload",
    response_model=ConfigReloadResponse,
    summary="Reload configuration caches",
    operation_id="reloadConfigCaches",
)
def reload_config_caches(
    admin: Annotated[User, Depends(get_admin_user)],
) -> ConfigReloadResponse:
    """Reload cached YAML configuration (admin only)."""
    logger.debug(f"Admin {admin.username} reloading config caches")
    ConfigLoader.clear_cache()
    clear_metrics_config_cache()
    clear_copilot_config_cache()
    clear_policy_config_cache()
    return ConfigReloadResponse(
        cleared=[
            "settings.yaml",
            "metrics.yaml",
            "copilot.yaml",
            "backend.yaml",
            "policy.yaml",
        ]
    )


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List all users",
    operation_id="listAllUsers",
)
def list_all_users(
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
    skip: int = 0,
    limit: int = 100,
) -> UserListResponse:
    """List all users in the system (admin only)."""
    logger.debug(f"Admin {admin.username} listing all users")
    return service.list_users(skip=skip, limit=limit)


@router.get(
    "/users/{username}",
    response_model=UserDetailResponse,
    summary="Get user details",
    operation_id="getUserDetails",
)
def get_user_details(
    username: str,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> UserDetailResponse:
    """Get detailed information about a specific user (admin only)."""
    logger.debug(f"Admin {admin.username} getting details for user {username}")
    return service.get_user_details(username)


@router.put(
    "/users/{username}",
    response_model=UserDetailResponse,
    summary="Update user settings",
    operation_id="updateUserSettings",
)
def update_user_settings(
    username: str,
    request: UpdateUserRequest,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> UserDetailResponse:
    """Update user settings (admin only)."""
    logger.debug(f"Admin {admin.username} updating user {username}")
    return service.update_user(
        username=username,
        admin_username=admin.username,
        full_name=request.full_name,
        disabled=request.disabled,
        system_role=request.system_role,
    )


@router.delete(
    "/users/{username}",
    summary="Delete user",
    operation_id="deleteUser",
)
def delete_user(
    username: str,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> dict[str, str]:
    """Delete a user account (admin only)."""
    logger.debug(f"Admin {admin.username} deleting user {username}")
    return service.delete_user(username=username, admin_username=admin.username)


# --- Project Management ---


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="List all projects",
    operation_id="listAllProjects",
)
def list_all_projects(
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
    skip: int = 0,
    limit: int = 100,
) -> ProjectListResponse:
    """List all projects in the system (admin only)."""
    logger.debug(f"Admin {admin.username} listing all projects")
    return service.list_projects(skip=skip, limit=limit)


@router.delete(
    "/projects/{project_id}",
    summary="Delete project",
    operation_id="adminDeleteProject",
)
def admin_delete_project(
    project_id: str,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> dict[str, str]:
    """Delete a project and all its memberships (admin only)."""
    logger.debug(f"Admin {admin.username} deleting project {project_id}")
    return service.delete_project(project_id=project_id, admin_username=admin.username)


# --- Member Management ---


@router.get(
    "/projects/{project_id}/members",
    response_model=MemberListResponse,
    summary="List project members",
    operation_id="listProjectMembersAdmin",
)
def list_project_members_admin(
    project_id: str,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MemberListResponse:
    """List all members of a project (admin only)."""
    logger.debug(f"Admin {admin.username} listing members for project {project_id}")
    return service.list_project_members(project_id)


@router.post(
    "/projects/{project_id}/members",
    response_model=MemberItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add member to project",
    operation_id="addProjectMemberAdmin",
)
def add_project_member_admin(
    project_id: str,
    request: AddMemberRequest,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> MemberItem:
    """Add a member to a project as viewer (admin only)."""
    logger.debug(f"Admin {admin.username} adding {request.username} to project {project_id}")
    return service.add_project_member(
        project_id=project_id,
        username=request.username,
        admin_username=admin.username,
    )


@router.delete(
    "/projects/{project_id}/members/{username}",
    summary="Remove member from project",
    operation_id="removeProjectMemberAdmin",
)
def remove_project_member_admin(
    project_id: str,
    username: str,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> dict[str, str]:
    """Remove a member from a project (admin only)."""
    logger.debug(f"Admin {admin.username} removing {username} from project {project_id}")
    return service.remove_project_member(project_id=project_id, username=username)


@router.post(
    "/users/{username}/project",
    response_model=UserDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create project for user",
    operation_id="createProjectForUser",
)
def create_project_for_user(
    username: str,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> UserDetailResponse:
    """Create a default project for a user who doesn't have one (admin only)."""
    logger.debug(f"Admin {admin.username} creating project for user {username}")
    return service.create_project_for_user(username)
