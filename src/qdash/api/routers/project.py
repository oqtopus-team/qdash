"""Project management API router."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.logger import logger
from qdash.api.lib.auth import get_current_active_user
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context_from_path,
    get_project_context_owner_from_path,
)
from qdash.api.lib.project_service import ProjectService
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
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument

router = APIRouter(
    prefix="/projects",
    tags=["projects"],
    responses={404: {"description": "Not found"}},
)


def _to_project_response(project: ProjectDocument) -> ProjectResponse:
    """Convert ProjectDocument to ProjectResponse."""
    return ProjectResponse(
        project_id=project.project_id,
        owner_username=project.owner_username,
        name=project.name,
        description=project.description,
        tags=project.tags,
        default_role=project.default_role,
        created_at=project.system_info.created_at,
        updated_at=project.system_info.updated_at,
    )


def _to_member_response(membership: ProjectMembershipDocument) -> MemberResponse:
    """Convert ProjectMembershipDocument to MemberResponse."""
    return MemberResponse(
        project_id=membership.project_id,
        username=membership.username,
        role=membership.role,
        status=membership.status,
        invited_by=membership.invited_by,
        last_accessed_at=membership.last_accessed_at,
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
) -> ProjectResponse:
    """Create a new project with the current user as owner."""
    logger.debug(f"Creating project '{project_data.name}' for user {current_user.username}")

    service = ProjectService()
    project = service.create_project(
        owner_username=current_user.username,
        name=project_data.name,
        description=project_data.description,
        tags=project_data.tags,
    )

    return _to_project_response(project)


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List user's projects",
    operation_id="listProjects",
)
def list_projects(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ProjectListResponse:
    """List all projects the user has access to."""
    logger.debug(f"Listing projects for user {current_user.username}")

    # Find all active memberships for this user
    memberships = list(ProjectMembershipDocument.find({"username": current_user.username, "status": "active"}).run())

    project_ids = [m.project_id for m in memberships]
    projects = list(ProjectDocument.find({"project_id": {"$in": project_ids}}).run())

    return ProjectListResponse(
        projects=[_to_project_response(p) for p in projects],
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
    return _to_project_response(ctx.project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project",
    operation_id="updateProject",
)
def update_project(
    project_data: ProjectUpdate,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
) -> ProjectResponse:
    """Update project settings. Owner only."""
    project = ctx.project

    if project_data.name is not None:
        project.name = project_data.name
    if project_data.description is not None:
        project.description = project_data.description
    if project_data.tags is not None:
        project.tags = project_data.tags
    if project_data.default_role is not None:
        project.default_role = project_data.default_role

    project.system_info.update_time()
    project.save()

    return _to_project_response(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project",
    operation_id="deleteProject",
)
def delete_project(
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
) -> None:
    """Delete a project. Owner only.

    Warning: This will delete the project but NOT the associated data.
    Data cleanup should be handled separately.
    """
    logger.warning(f"Deleting project {ctx.project_id} by user {ctx.user.username}")

    # Delete all memberships
    ProjectMembershipDocument.find({"project_id": ctx.project_id}).delete().run()

    # Delete project
    ctx.project.delete()


# --- Member Management ---


@router.get(
    "/{project_id}/members",
    response_model=MemberListResponse,
    summary="List project members",
    operation_id="listProjectMembers",
)
def list_members(
    ctx: Annotated[ProjectContext, Depends(get_project_context_from_path)],
) -> MemberListResponse:
    """List all members of a project."""
    memberships = list(ProjectMembershipDocument.find({"project_id": ctx.project_id}).run())

    return MemberListResponse(
        members=[_to_member_response(m) for m in memberships],
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
    invite_data: MemberInvite,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
) -> MemberResponse:
    """Invite a user to the project. Owner only."""
    # Check if user exists
    target_user = UserDocument.find_one({"username": invite_data.username}).run()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{invite_data.username}' not found",
        )

    # Check if already a member
    existing = ProjectMembershipDocument.find_one(
        {"project_id": ctx.project_id, "username": invite_data.username}
    ).run()

    if existing:
        if existing.status == "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User '{invite_data.username}' is already a member",
            )
        # Reactivate if revoked
        existing.role = invite_data.role
        existing.status = "active"
        existing.invited_by = ctx.user.username
        existing.system_info.update_time()
        existing.save()
        return _to_member_response(existing)

    # Create new membership
    membership = ProjectMembershipDocument(
        project_id=ctx.project_id,
        username=invite_data.username,
        role=invite_data.role,
        status="active",  # Directly active for now (no invitation flow)
        invited_by=ctx.user.username,
    )
    membership.insert()

    logger.info(
        f"User {ctx.user.username} invited {invite_data.username} " f"to project {ctx.project_id} as {invite_data.role}"
    )

    return _to_member_response(membership)


@router.patch(
    "/{project_id}/members/{username}",
    response_model=MemberResponse,
    summary="Update member role",
    operation_id="updateProjectMember",
)
def update_member(
    username: str,
    update_data: MemberUpdate,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
) -> MemberResponse:
    """Update a member's role. Owner only."""
    if username == ctx.project.owner_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the owner's role",
        )

    membership = ProjectMembershipDocument.find_one({"project_id": ctx.project_id, "username": username}).run()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member '{username}' not found in project",
        )

    membership.role = update_data.role
    membership.system_info.update_time()
    membership.save()

    return _to_member_response(membership)


@router.delete(
    "/{project_id}/members/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove member",
    operation_id="removeProjectMember",
)
def remove_member(
    username: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
) -> None:
    """Remove a member from the project. Owner only."""
    if username == ctx.project.owner_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the project owner",
        )

    membership = ProjectMembershipDocument.find_one({"project_id": ctx.project_id, "username": username}).run()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Member '{username}' not found in project",
        )

    membership.status = "revoked"
    membership.system_info.update_time()
    membership.save()

    logger.info(f"User {ctx.user.username} removed {username} from project {ctx.project_id}")


# --- Transfer ownership ---


@router.post(
    "/{project_id}/transfer",
    response_model=ProjectResponse,
    summary="Transfer project ownership",
    operation_id="transferProjectOwnership",
)
def transfer_ownership(
    new_owner: MemberInvite,
    ctx: Annotated[ProjectContext, Depends(get_project_context_owner_from_path)],
) -> ProjectResponse:
    """Transfer project ownership to another user. Current owner only."""
    if new_owner.username == ctx.project.owner_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already the owner",
        )

    # Ensure new owner exists
    target_user = UserDocument.find_one({"username": new_owner.username}).run()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{new_owner.username}' not found",
        )

    # Update old owner membership to editor
    old_owner_membership = ProjectMembershipDocument.find_one(
        {"project_id": ctx.project_id, "username": ctx.project.owner_username}
    ).run()
    if old_owner_membership:
        old_owner_membership.role = ProjectRole.EDITOR
        old_owner_membership.system_info.update_time()
        old_owner_membership.save()

    # Update or create new owner membership
    new_owner_membership = ProjectMembershipDocument.find_one(
        {"project_id": ctx.project_id, "username": new_owner.username}
    ).run()

    if new_owner_membership:
        new_owner_membership.role = ProjectRole.OWNER
        new_owner_membership.status = "active"
        new_owner_membership.system_info.update_time()
        new_owner_membership.save()
    else:
        new_owner_membership = ProjectMembershipDocument(
            project_id=ctx.project_id,
            username=new_owner.username,
            role=ProjectRole.OWNER,
            status="active",
            invited_by=ctx.user.username,
        )
        new_owner_membership.insert()

    # Update project owner
    ctx.project.owner_username = new_owner.username
    ctx.project.system_info.update_time()
    ctx.project.save()

    logger.warning(
        f"Project {ctx.project_id} ownership transferred from " f"{ctx.user.username} to {new_owner.username}"
    )

    return _to_project_response(ctx.project)
