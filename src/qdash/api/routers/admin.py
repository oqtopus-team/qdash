"""Admin router for user and system management."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
    ProjectListItem,
    ProjectListResponse,
    UpdateUserRequest,
    UserDetailResponse,
    UserListItem,
    UserListResponse,
)
from qdash.api.schemas.auth import User
from qdash.datamodel.project import ProjectRole
from qdash.datamodel.user import SystemRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

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
    skip: int = 0,
    limit: int = 100,
) -> UserListResponse:
    """List all users in the system (admin only).

    Parameters
    ----------
    admin : User
        Current admin user (verified by dependency)
    skip : int
        Number of users to skip for pagination
    limit : int
        Maximum number of users to return

    Returns
    -------
    UserListResponse
        List of users with total count

    """
    from qdash.dbmodel.project import ProjectDocument

    logger.debug(f"Admin {admin.username} listing all users")

    # Get total count
    total = UserDocument.find_all().count()

    # Get paginated users
    users = list(UserDocument.find_all().skip(skip).limit(limit).run())

    # Build a map of owner_username -> project_id for users who own projects
    usernames = [u.username for u in users]
    projects = list(ProjectDocument.find({"owner_username": {"$in": usernames}}).run())
    owner_project_map = {p.owner_username: p.project_id for p in projects}

    user_list = []
    for u in users:
        # Use default_project_id if set, otherwise check if user owns a project
        project_id = u.default_project_id or owner_project_map.get(u.username)
        user_list.append(
            UserListItem(
                username=u.username,
                full_name=u.full_name,
                disabled=u.disabled,
                system_role=u.system_role,
                default_project_id=project_id,
            )
        )

    return UserListResponse(users=user_list, total=total)


@router.get(
    "/users/{username}",
    response_model=UserDetailResponse,
    summary="Get user details",
    operation_id="getUserDetails",
)
def get_user_details(
    username: str,
    admin: Annotated[User, Depends(get_admin_user)],
) -> UserDetailResponse:
    """Get detailed information about a specific user (admin only).

    Parameters
    ----------
    username : str
        Username to look up
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    UserDetailResponse
        Detailed user information

    Raises
    ------
    HTTPException
        404 if user not found

    """
    logger.debug(f"Admin {admin.username} getting details for user {username}")

    user = UserDocument.find_one({"username": username}).run()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )

    return UserDetailResponse(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled,
        system_role=user.system_role,
        default_project_id=user.default_project_id,
        created_at=user.system_info.created_at if user.system_info else None,
        updated_at=user.system_info.updated_at if user.system_info else None,
    )


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
) -> UserDetailResponse:
    """Update user settings (admin only).

    Parameters
    ----------
    username : str
        Username to update
    request : UpdateUserRequest
        Update request with fields to modify
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    UserDetailResponse
        Updated user information

    Raises
    ------
    HTTPException
        404 if user not found
        400 if trying to demote the last admin

    """
    logger.debug(f"Admin {admin.username} updating user {username}")

    user = UserDocument.find_one({"username": username}).run()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )

    # Prevent demoting the last admin (check this first for clearer error message)
    if request.system_role is not None and request.system_role != user.system_role:
        if user.system_role == SystemRole.ADMIN:
            admin_count = UserDocument.find({"system_role": SystemRole.ADMIN}).count()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the last admin user",
                )

    # Prevent admin from changing their own role
    if request.system_role is not None and username == admin.username:
        if request.system_role != user.system_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own system role",
            )

    # Update fields if provided
    if request.full_name is not None:
        user.full_name = request.full_name
    if request.disabled is not None:
        user.disabled = request.disabled
    if request.system_role is not None:
        user.system_role = request.system_role

    # Update timestamp
    if user.system_info:
        from datetime import datetime, timezone

        user.system_info.updated_at = datetime.now(timezone.utc).isoformat()

    user.save()
    logger.debug(f"User {username} updated successfully")

    return UserDetailResponse(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled,
        system_role=user.system_role,
        default_project_id=user.default_project_id,
        created_at=user.system_info.created_at if user.system_info else None,
        updated_at=user.system_info.updated_at if user.system_info else None,
    )


@router.delete(
    "/users/{username}",
    summary="Delete user",
    operation_id="deleteUser",
)
def delete_user(
    username: str,
    admin: Annotated[User, Depends(get_admin_user)],
) -> dict[str, str]:
    """Delete a user account (admin only).

    Parameters
    ----------
    username : str
        Username to delete
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    dict[str, str]
        Success message

    Raises
    ------
    HTTPException
        404 if user not found
        400 if trying to delete self or last admin

    """
    logger.debug(f"Admin {admin.username} deleting user {username}")

    # Prevent self-deletion
    if username == admin.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    user = UserDocument.find_one({"username": username}).run()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )

    # Prevent deleting the last admin
    if user.system_role == SystemRole.ADMIN:
        admin_count = UserDocument.find({"system_role": SystemRole.ADMIN}).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last admin user",
            )

    user.delete()
    logger.debug(f"User {username} deleted successfully")

    return {"message": f"User '{username}' deleted successfully"}


# --- Project Management ---


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="List all projects",
    operation_id="listAllProjects",
)
def list_all_projects(
    admin: Annotated[User, Depends(get_admin_user)],
    skip: int = 0,
    limit: int = 100,
) -> ProjectListResponse:
    """List all projects in the system (admin only).

    Parameters
    ----------
    admin : User
        Current admin user (verified by dependency)
    skip : int
        Number of projects to skip for pagination
    limit : int
        Maximum number of projects to return

    Returns
    -------
    ProjectListResponse
        List of projects with total count

    """
    logger.debug(f"Admin {admin.username} listing all projects")

    # Get total count
    total = ProjectDocument.find_all().count()

    # Get paginated projects
    projects = list(ProjectDocument.find_all().skip(skip).limit(limit).run())

    project_list = []
    for p in projects:
        # Count members for each project
        member_count = ProjectMembershipDocument.find({"project_id": p.project_id}).count()
        project_list.append(
            ProjectListItem(
                project_id=p.project_id,
                name=p.name,
                owner_username=p.owner_username,
                description=p.description,
                member_count=member_count,
                created_at=p.system_info.created_at if p.system_info else None,
            )
        )

    return ProjectListResponse(projects=project_list, total=total)


@router.delete(
    "/projects/{project_id}",
    summary="Delete project",
    operation_id="adminDeleteProject",
)
def admin_delete_project(
    project_id: str,
    admin: Annotated[User, Depends(get_admin_user)],
) -> dict[str, str]:
    """Delete a project and all its memberships (admin only).

    Parameters
    ----------
    project_id : str
        Project ID to delete
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    dict[str, str]
        Success message

    Raises
    ------
    HTTPException
        404 if project not found
        400 if trying to delete own project

    """
    logger.debug(f"Admin {admin.username} deleting project {project_id}")

    project = ProjectDocument.find_one({"project_id": project_id}).run()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    # Prevent admin from deleting their own project
    if project.owner_username == admin.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own project",
        )

    # Delete all memberships for this project
    ProjectMembershipDocument.find({"project_id": project_id}).delete().run()

    # Clear default_project_id from users who have this as default
    UserDocument.find({"default_project_id": project_id}).update_many(
        {"$set": {"default_project_id": None}}
    ).run()

    # Delete the project
    project.delete()
    logger.info(f"Admin {admin.username} deleted project {project_id} ({project.name})")

    return {"message": f"Project '{project.name}' deleted successfully"}


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
) -> MemberListResponse:
    """List all members of a project (admin only).

    Parameters
    ----------
    project_id : str
        Project ID to list members for
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    MemberListResponse
        List of members with total count

    Raises
    ------
    HTTPException
        404 if project not found

    """
    logger.debug(f"Admin {admin.username} listing members for project {project_id}")

    project = ProjectDocument.find_one({"project_id": project_id}).run()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    memberships = list(
        ProjectMembershipDocument.find({"project_id": project_id, "status": "active"}).run()
    )

    # Get user details for each member
    members = []
    for m in memberships:
        user = UserDocument.find_one({"username": m.username}).run()
        members.append(
            MemberItem(
                username=m.username,
                full_name=user.full_name if user else None,
                role=m.role,
                status=m.status,
            )
        )

    return MemberListResponse(members=members, total=len(members))


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
) -> MemberItem:
    """Add a member to a project as viewer (admin only).

    Parameters
    ----------
    project_id : str
        Project ID to add member to
    request : AddMemberRequest
        Member details (username)
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    MemberItem
        Created member info

    Raises
    ------
    HTTPException
        404 if project or user not found
        400 if user is already a member

    """
    logger.debug(f"Admin {admin.username} adding {request.username} to project {project_id}")

    project = ProjectDocument.find_one({"project_id": project_id}).run()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    user = UserDocument.find_one({"username": request.username}).run()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{request.username}' not found",
        )

    # Check if already a member
    existing = ProjectMembershipDocument.find_one(
        {"project_id": project_id, "username": request.username}
    ).run()

    if existing:
        if existing.status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User '{request.username}' is already a member",
            )
        # Reactivate revoked membership as viewer
        existing.role = ProjectRole.VIEWER
        existing.status = "active"
        existing.invited_by = admin.username
        existing.system_info.update_time()
        existing.save()
        logger.info(
            f"Admin {admin.username} reactivated {request.username} in project {project_id} as viewer"
        )
        return MemberItem(
            username=existing.username,
            full_name=user.full_name,
            role=existing.role,
            status=existing.status,
        )

    # Create new membership as viewer
    from qdash.datamodel.system_info import SystemInfoModel

    membership = ProjectMembershipDocument(
        project_id=project_id,
        username=request.username,
        role=ProjectRole.VIEWER,
        status="active",
        invited_by=admin.username,
        system_info=SystemInfoModel(),
    )
    membership.insert()

    logger.info(
        f"Admin {admin.username} added {request.username} to project {project_id} as viewer"
    )

    return MemberItem(
        username=membership.username,
        full_name=user.full_name,
        role=membership.role,
        status=membership.status,
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
) -> dict[str, str]:
    """Remove a member from a project (admin only).

    Parameters
    ----------
    project_id : str
        Project ID to remove member from
    username : str
        Username to remove
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    dict[str, str]
        Success message

    Raises
    ------
    HTTPException
        404 if project or member not found
        400 if trying to remove the owner

    """
    logger.debug(f"Admin {admin.username} removing {username} from project {project_id}")

    project = ProjectDocument.find_one({"project_id": project_id}).run()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    # Prevent removing the owner
    if project.owner_username == username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the project owner",
        )

    membership = ProjectMembershipDocument.find_one(
        {"project_id": project_id, "username": username, "status": "active"}
    ).run()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member '{username}' not found in project",
        )

    membership.status = "revoked"
    membership.system_info.update_time()
    membership.save()

    logger.info(f"Admin {admin.username} removed {username} from project {project_id}")

    return {"message": f"Member '{username}' removed from project"}


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
) -> UserDetailResponse:
    """Create a default project for a user who doesn't have one (admin only).

    Parameters
    ----------
    username : str
        Username to create project for
    admin : User
        Current admin user (verified by dependency)

    Returns
    -------
    UserDetailResponse
        Updated user information with new project

    Raises
    ------
    HTTPException
        404 if user not found
        400 if user already has a project

    """
    from qdash.api.lib.project_service import ProjectService
    from qdash.dbmodel.project import ProjectDocument

    logger.debug(f"Admin {admin.username} creating project for user {username}")

    user = UserDocument.find_one({"username": username}).run()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found",
        )

    # Check if user already owns a project
    existing_project = ProjectDocument.find_one({"owner_username": username}).run()
    if existing_project:
        # User already owns a project, just update their default_project_id
        user.default_project_id = existing_project.project_id
        if user.system_info:
            from datetime import datetime, timezone

            user.system_info.updated_at = datetime.now(timezone.utc).isoformat()
        user.save()
        logger.info(f"Linked existing project to user {username}")
        return UserDetailResponse(
            username=user.username,
            full_name=user.full_name,
            disabled=user.disabled,
            system_role=user.system_role,
            default_project_id=user.default_project_id,
            created_at=user.system_info.created_at if user.system_info else None,
            updated_at=user.system_info.updated_at if user.system_info else None,
        )

    if user.default_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User '{username}' already has a project",
        )

    # Create project for user
    service = ProjectService()
    project = service.create_project(
        owner_username=username,
        name=f"{username}'s project",
    )

    # Update user's default_project_id
    user.default_project_id = project.project_id
    if user.system_info:
        from datetime import datetime, timezone

        user.system_info.updated_at = datetime.now(timezone.utc).isoformat()
    user.save()

    logger.info(f"Admin {admin.username} created project for user {username}")

    return UserDetailResponse(
        username=user.username,
        full_name=user.full_name,
        disabled=user.disabled,
        system_role=user.system_role,
        default_project_id=user.default_project_id,
        created_at=user.system_info.created_at if user.system_info else None,
        updated_at=user.system_info.updated_at if user.system_info else None,
    )
