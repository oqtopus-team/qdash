"""Project permission dependencies for API endpoints."""

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path, status
from qdash.api.lib.auth import get_current_active_user, get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument

logger = logging.getLogger(__name__)


@dataclass
class ProjectContext:
    """Context object containing project and user information."""

    project_id: str
    project: ProjectDocument
    user: User
    role: ProjectRole


def get_project_id_from_header(
    x_project_id: Annotated[str | None, Header(alias="X-Project-Id")] = None,
) -> str | None:
    """Extract project_id from X-Project-Id header."""
    return x_project_id


def get_project_id_from_path(
    project_id: Annotated[str, Path(description="Project identifier")],
) -> str:
    """Extract project_id from path parameter."""
    return project_id


def _resolve_project_id(
    user: User,
    project_id_header: str | None = None,
    project_id_path: str | None = None,
) -> str:
    """Resolve the effective project_id from various sources.

    Priority:
    1. Path parameter (explicit)
    2. Header (X-Project-Id)
    3. User's default project
    4. User's owned project (fallback)
    """
    if project_id_path:
        return project_id_path
    if project_id_header:
        return project_id_header
    if user.default_project_id:
        return user.default_project_id

    # Fallback: check if user owns a project
    from qdash.dbmodel.project import ProjectDocument

    owned_project = ProjectDocument.find_one({"owner_username": user.username}).run()
    if owned_project:
        return owned_project.project_id

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Project ID is required. Provide via X-Project-Id header or path parameter.",
    )


def _get_membership(project_id: str, username: str) -> ProjectMembershipDocument | None:
    """Get active membership for user in project."""
    return ProjectMembershipDocument.get_active_membership(project_id, username)


def _check_permission(
    project_id: str,
    user: User,
    required_roles: list[ProjectRole] | None = None,
) -> tuple[ProjectDocument, ProjectRole]:
    """Check if user has permission to access project.

    Args:
        project_id: The project identifier
        user: The authenticated user
        required_roles: List of roles that are allowed. If None, any role is accepted.

    Returns:
        Tuple of (ProjectDocument, user's role)

    Raises:
        HTTPException: If project not found or user lacks permission
    """
    # Find project
    project = ProjectDocument.find_by_id(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )

    # Check membership
    membership = _get_membership(project_id, user.username)
    if not membership:
        # Check if user is the owner (fallback for legacy data)
        if project.owner_username == user.username:
            logger.debug(f"User {user.username} is owner of project {project_id}")
            return project, ProjectRole.OWNER
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have access to project '{project_id}'",
        )

    # Check role if required
    if required_roles and membership.role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {[r.value for r in required_roles]}",
        )

    return project, membership.role


def get_project_context(
    user: Annotated[User, Depends(get_current_active_user)],
    project_id_header: Annotated[str | None, Depends(get_project_id_from_header)] = None,
) -> ProjectContext:
    """Get project context with viewer or higher permission.

    Use this dependency for read-only endpoints.
    """
    project_id = _resolve_project_id(user, project_id_header)
    project, role = _check_permission(project_id, user)
    return ProjectContext(project_id=project_id, project=project, user=user, role=role)


def get_project_context_owner(
    user: Annotated[User, Depends(get_current_active_user)],
    project_id_header: Annotated[str | None, Depends(get_project_id_from_header)] = None,
) -> ProjectContext:
    """Get project context with owner permission only.

    Use this dependency for admin endpoints (e.g., project settings, member management).
    """
    project_id = _resolve_project_id(user, project_id_header)
    project, role = _check_permission(project_id, user, required_roles=[ProjectRole.OWNER])
    return ProjectContext(project_id=project_id, project=project, user=user, role=role)


def get_optional_project_context(
    user: Annotated[User, Depends(get_optional_current_user)],
    project_id_header: Annotated[str | None, Depends(get_project_id_from_header)] = None,
) -> ProjectContext | None:
    """Get project context if project_id is provided, otherwise return None.

    Use this for endpoints that can work with or without project scope.
    """
    project_id = project_id_header or user.default_project_id
    if not project_id:
        return None

    try:
        project, role = _check_permission(project_id, user)
        return ProjectContext(project_id=project_id, project=project, user=user, role=role)
    except HTTPException:
        return None


# --- Path-based dependencies for /projects/{project_id} endpoints ---


def get_project_context_from_path(
    project_id: Annotated[str, Path(description="Project identifier")],
    user: Annotated[User, Depends(get_current_active_user)],
) -> ProjectContext:
    """Get project context from path parameter with viewer or higher permission.

    Use this dependency for project router read endpoints with /{project_id}.
    """
    project, role = _check_permission(project_id, user)
    return ProjectContext(project_id=project_id, project=project, user=user, role=role)


def get_project_context_owner_from_path(
    project_id: Annotated[str, Path(description="Project identifier")],
    user: Annotated[User, Depends(get_current_active_user)],
) -> ProjectContext:
    """Get project context from path parameter with owner permission only.

    Use this dependency for project router admin endpoints with /{project_id}.
    """
    project, role = _check_permission(project_id, user, required_roles=[ProjectRole.OWNER])
    return ProjectContext(project_id=project_id, project=project, user=user, role=role)
