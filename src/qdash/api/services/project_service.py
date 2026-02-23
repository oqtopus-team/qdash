"""Service for project and membership management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException, status
from qdash.api.schemas.project import MemberResponse, ProjectResponse
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.repository import (
    MongoProjectMembershipRepository,
    MongoProjectRepository,
    MongoUserRepository,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)


class ProjectService:
    """Service for project lifecycle and membership operations."""

    def __init__(
        self,
        project_repo: MongoProjectRepository | None = None,
        membership_repo: MongoProjectMembershipRepository | None = None,
        user_repo: MongoUserRepository | None = None,
    ) -> None:
        """Initialize the service with repositories.

        Repositories default to new instances if not provided,
        for backward compatibility with ``ProjectService()`` usage.
        """
        self._project_repo = project_repo or MongoProjectRepository()
        self._membership_repo = membership_repo or MongoProjectMembershipRepository()
        self._user_repo = user_repo or MongoUserRepository()

    @staticmethod
    def to_project_response(project: ProjectDocument) -> ProjectResponse:
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

    @staticmethod
    def to_member_response(
        membership: ProjectMembershipDocument,
    ) -> MemberResponse:
        """Convert ProjectMembershipDocument to MemberResponse."""
        return MemberResponse(
            project_id=membership.project_id,
            username=membership.username,
            role=membership.role,
            status=membership.status,
            invited_by=membership.invited_by,
            last_accessed_at=membership.last_accessed_at,
        )

    def create_project(
        self,
        owner_username: str,
        name: str,
        description: str | None = None,
        tags: Iterable[str] | None = None,
        default_role: ProjectRole = ProjectRole.VIEWER,
    ) -> ProjectDocument:
        """Create a project and register owner membership.

        Parameters
        ----------
        owner_username : str
            Username of the project owner.
        name : str
            Project name.
        description : str | None
            Project description.
        tags : Iterable[str] | None
            Project tags.
        default_role : ProjectRole
            Default role for new members.

        Returns
        -------
        ProjectDocument
            The created project.

        """
        project = ProjectDocument(
            owner_username=owner_username,
            name=name,
            description=description,
            tags=list(tags or []),
            default_role=default_role,
        )
        project.insert()
        logger.debug("Created project %s for %s", project.project_id, owner_username)
        self._ensure_membership(
            project_id=project.project_id,
            username=owner_username,
            role=ProjectRole.OWNER,
            status="active",
        )
        return project

    def ensure_default_project(self, user: UserDocument) -> ProjectDocument:
        """Ensure the given user has a default project and return it.

        Parameters
        ----------
        user : UserDocument
            The user document.

        Returns
        -------
        ProjectDocument
            The user's default project.

        """
        if user.default_project_id:
            existing = ProjectDocument.find_by_id(user.default_project_id)
            if existing:
                self._ensure_membership(
                    project_id=existing.project_id,
                    username=user.username,
                    role=ProjectRole.OWNER,
                    status="active",
                )
                return cast(ProjectDocument, existing)
            logger.warning(
                "Default project %s missing for user %s, creating a new one",
                user.default_project_id,
                user.username,
            )

        project_name = f"{user.username}'s project"
        new_project = self.create_project(owner_username=user.username, name=project_name)
        user.default_project_id = new_project.project_id
        user.system_info.update_time()
        user.save()
        return new_project

    def set_user_default_project(self, user: UserDocument, project_id: str) -> None:
        """Set the default project for a user and persist.

        Parameters
        ----------
        user : UserDocument
            The user document.
        project_id : str
            The project ID to set as default.

        """
        user.default_project_id = project_id
        self._user_repo.save(user)

    def list_projects(self, username: str) -> list[ProjectDocument]:
        """List all projects the user has access to.

        Parameters
        ----------
        username : str
            The username to list projects for.

        Returns
        -------
        list[ProjectDocument]
            List of projects.

        """
        memberships = self._membership_repo.find_by_username(username, status="active")
        project_ids = [m.project_id for m in memberships]
        return self._project_repo.find({"project_id": {"$in": project_ids}})

    def update_project(self, project: ProjectDocument, data: dict[str, Any]) -> ProjectDocument:
        """Update project fields.

        Parameters
        ----------
        project : ProjectDocument
            The project to update.
        data : dict
            Fields to update (name, description, tags, default_role).

        Returns
        -------
        ProjectDocument
            The updated project.

        """
        if data.get("name") is not None:
            project.name = data["name"]
        if data.get("description") is not None:
            project.description = data["description"]
        if data.get("tags") is not None:
            project.tags = data["tags"]
        if data.get("default_role") is not None:
            project.default_role = data["default_role"]

        project.system_info.update_time()
        project.save()
        return project

    def delete_project(self, project_id: str, project: ProjectDocument) -> None:
        """Delete a project and its memberships.

        Parameters
        ----------
        project_id : str
            The project ID.
        project : ProjectDocument
            The project document to delete.

        """
        self._membership_repo.delete_by_project(project_id)
        project.delete()

    def list_members(self, project_id: str) -> list[ProjectMembershipDocument]:
        """List all members of a project.

        Parameters
        ----------
        project_id : str
            The project ID.

        Returns
        -------
        list[ProjectMembershipDocument]
            List of memberships.

        """
        return self._membership_repo.find_by_project(project_id)

    def invite_member(
        self,
        project_id: str,
        username: str,
        role: ProjectRole,
        admin_username: str,
    ) -> ProjectMembershipDocument:
        """Invite a user to a project.

        Parameters
        ----------
        project_id : str
            The project ID.
        username : str
            The username to invite.
        role : ProjectRole
            The role to assign.
        admin_username : str
            The admin performing the invitation.

        Returns
        -------
        ProjectMembershipDocument
            The created or updated membership.

        Raises
        ------
        HTTPException
            404 if project or user not found.
            409 if user is already an active member.

        """
        project = self._project_repo.find_one({"project_id": project_id})
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        target_user = self._user_repo.find_one({"username": username})
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{username}' not found",
            )

        existing = self._membership_repo.find_one({"project_id": project_id, "username": username})

        if existing:
            if existing.status == "active":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User '{username}' is already a member",
                )
            existing.role = role
            existing.status = "active"
            existing.invited_by = admin_username
            existing.system_info.update_time()
            self._membership_repo.save(existing)
            return existing

        membership = self._membership_repo.create_membership(
            project_id=project_id,
            username=username,
            role=role,
            status="active",
            invited_by=admin_username,
        )

        logger.info(f"Admin {admin_username} invited {username} to project {project_id} as {role}")
        return membership

    def update_member(
        self,
        project_id: str,
        username: str,
        role: ProjectRole,
    ) -> ProjectMembershipDocument:
        """Update a member's role.

        Parameters
        ----------
        project_id : str
            The project ID.
        username : str
            The member's username.
        role : ProjectRole
            The new role.

        Returns
        -------
        ProjectMembershipDocument
            The updated membership.

        Raises
        ------
        HTTPException
            404 if project or member not found.
            400 if trying to change the owner's role.

        """
        project = self._project_repo.find_one({"project_id": project_id})
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        if username == project.owner_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change the owner's role",
            )

        membership = self._membership_repo.find_one(
            {"project_id": project_id, "username": username}
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member '{username}' not found in project",
            )

        membership.role = role
        membership.system_info.update_time()
        self._membership_repo.save(membership)
        return membership

    def remove_member(
        self,
        project_id: str,
        username: str,
        admin_username: str,
    ) -> None:
        """Remove a member from a project.

        Parameters
        ----------
        project_id : str
            The project ID.
        username : str
            The member's username.
        admin_username : str
            The admin performing the removal.

        Raises
        ------
        HTTPException
            404 if project or member not found.
            400 if trying to remove the owner.

        """
        project = self._project_repo.find_one({"project_id": project_id})
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        if username == project.owner_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the project owner",
            )

        membership = self._membership_repo.find_one(
            {"project_id": project_id, "username": username}
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member '{username}' not found in project",
            )

        membership.status = "revoked"
        membership.system_info.update_time()
        self._membership_repo.save(membership)

        logger.info(f"Admin {admin_username} removed {username} from project {project_id}")

    def transfer_ownership(
        self,
        project_id: str,
        new_owner_username: str,
        admin_username: str,
    ) -> ProjectDocument:
        """Transfer project ownership to another user.

        Parameters
        ----------
        project_id : str
            The project ID.
        new_owner_username : str
            The new owner's username.
        admin_username : str
            The admin performing the transfer.

        Returns
        -------
        ProjectDocument
            The updated project.

        Raises
        ------
        HTTPException
            404 if project or user not found.
            400 if new owner is already the owner.

        """
        project = self._project_repo.find_one({"project_id": project_id})
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )

        if new_owner_username == project.owner_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already the owner",
            )

        target_user = self._user_repo.find_one({"username": new_owner_username})
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{new_owner_username}' not found",
            )

        # Update old owner membership to viewer
        old_owner_membership = self._membership_repo.find_one(
            {"project_id": project_id, "username": project.owner_username}
        )
        if old_owner_membership:
            old_owner_membership.role = ProjectRole.VIEWER
            old_owner_membership.system_info.update_time()
            self._membership_repo.save(old_owner_membership)

        # Update or create new owner membership
        new_owner_membership = self._membership_repo.find_one(
            {"project_id": project_id, "username": new_owner_username}
        )

        if new_owner_membership:
            new_owner_membership.role = ProjectRole.OWNER
            new_owner_membership.status = "active"
            new_owner_membership.system_info.update_time()
            self._membership_repo.save(new_owner_membership)
        else:
            self._membership_repo.create_membership(
                project_id=project_id,
                username=new_owner_username,
                role=ProjectRole.OWNER,
                status="active",
                invited_by=admin_username,
            )

        # Update project owner
        project.owner_username = new_owner_username
        project.system_info.update_time()
        self._project_repo.save(project)

        logger.warning(
            f"Admin {admin_username} transferred project "
            f"{project_id} ownership to {new_owner_username}"
        )

        return project

    def invite_viewer(
        self, project_id: str, username: str, invited_by: str
    ) -> ProjectMembershipDocument:
        """Create/update a pending viewer membership invitation."""
        return self._ensure_membership(
            project_id=project_id,
            username=username,
            role=ProjectRole.VIEWER,
            status="pending",
            invited_by=invited_by,
        )

    def _ensure_membership(
        self,
        project_id: str,
        username: str,
        role: ProjectRole,
        status: str = "pending",
        invited_by: str | None = None,
    ) -> ProjectMembershipDocument:
        """Insert or update a membership entry."""
        membership = ProjectMembershipDocument.find_one(
            {"project_id": project_id, "username": username}
        ).run()
        if membership:
            membership.role = role
            membership.status = status
            membership.invited_by = invited_by
            membership.system_info.update_time()
            membership.save()
            return membership

        membership = ProjectMembershipDocument(
            project_id=project_id,
            username=username,
            role=role,
            status=status,
            invited_by=invited_by,
        )
        membership.insert()
        return membership
