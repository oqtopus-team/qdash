"""Project management API router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from qdash.api.dependencies import get_project_service
from qdash.api.lib.auth import get_admin_user, get_current_active_user
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context_from_path,
    get_project_context_owner_from_path,
)
from qdash.api.schemas.auth import User
from qdash.api.schemas.project import (
    MemberInvite,
    MemberListResponse,
    MemberResponse,
    MemberUpdate,
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from qdash.api.services.project_service import ProjectService
from qdash.datamodel.user import SystemRole

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    responses={404: {"description": "Not found"}},
)


# --- Project CRUD ---


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
    operation_id="createProject",
)
def create_project(
    project_data: ProjectCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Create a new project with the current user as owner."""
    logger.debug(f"Creating project '{project_data.name}' for user {current_user.username}")

    if current_user.system_role != SystemRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create projects.",
        )

    project = service.create_project(
        owner_username=current_user.username,
        name=project_data.name,
        description=project_data.description,
        tags=project_data.tags,
    )

    return ProjectService.to_project_response(project)


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List user's projects",
    operation_id="listProjects",
)
def list_projects(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectListResponse:
    """List all projects the user has access to."""
    logger.debug(f"Listing projects for user {current_user.username}")

    projects = service.list_projects(current_user.username)

    return ProjectListResponse(
        projects=[ProjectService.to_project_response(p) for p in projects],
        total=len(projects),
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details",
    operation_id="getProject",
)
def get_project(
    ctx: Annotated[ProjectContext, Depends(get_project_context_from_path)],
) -> ProjectResponse:
    """Get details of a specific project."""
    return ProjectService.to_project_response(ctx.project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project",
    operation_id="updateProject",
)
def update_project(
    project_data: ProjectUpdate,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Update project settings. Owner only."""
    project = service.update_project(
        ctx.project,
        {
            "name": project_data.name,
            "description": project_data.description,
            "tags": project_data.tags,
            "default_role": project_data.default_role,
        },
    )
    return ProjectService.to_project_response(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project",
    operation_id="deleteProject",
)
def delete_project(
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> None:
    """Delete a project. Owner only."""
    logger.warning(f"Deleting project {ctx.project_id} by user {ctx.user.username}")
    service.delete_project(ctx.project_id, ctx.project)


# --- Member Management ---


@router.get(
    "/{project_id}/members",
    response_model=MemberListResponse,
    summary="List project members",
    operation_id="listProjectMembers",
)
def list_members(
    ctx: Annotated[ProjectContext, Depends(get_project_context_from_path)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> MemberListResponse:
    """List all members of a project."""
    memberships = service.list_members(ctx.project_id)

    return MemberListResponse(
        members=[ProjectService.to_member_response(m) for m in memberships],
        total=len(memberships),
    )


@router.post(
    "/{project_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a member",
    operation_id="inviteProjectMember",
)
def invite_member(
    project_id: str,
    invite_data: MemberInvite,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> MemberResponse:
    """Invite a user to the project. Admin only."""
    membership = service.invite_member(
        project_id=project_id,
        username=invite_data.username,
        role=invite_data.role,
        admin_username=admin.username,
    )
    return ProjectService.to_member_response(membership)


@router.patch(
    "/{project_id}/members/{username}",
    response_model=MemberResponse,
    summary="Update member role",
    operation_id="updateProjectMember",
)
def update_member(
    project_id: str,
    username: str,
    update_data: MemberUpdate,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> MemberResponse:
    """Update a member's role. Admin only."""
    membership = service.update_member(
        project_id=project_id,
        username=username,
        role=update_data.role,
    )
    return ProjectService.to_member_response(membership)


@router.delete(
    "/{project_id}/members/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove member",
    operation_id="removeProjectMember",
)
def remove_member(
    project_id: str,
    username: str,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> None:
    """Remove a member from the project. Admin only."""
    service.remove_member(
        project_id=project_id,
        username=username,
        admin_username=admin.username,
    )


# --- Transfer ownership ---


@router.post(
    "/{project_id}/transfer",
    response_model=ProjectResponse,
    summary="Transfer project ownership",
    operation_id="transferProjectOwnership",
)
def transfer_ownership(
    project_id: str,
    new_owner: MemberInvite,
    admin: Annotated[User, Depends(get_admin_user)],
    service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    """Transfer project ownership to another user. Admin only."""
    project = service.transfer_ownership(
        project_id=project_id,
        new_owner_username=new_owner.username,
        admin_username=admin.username,
    )
    return ProjectService.to_project_response(project)
