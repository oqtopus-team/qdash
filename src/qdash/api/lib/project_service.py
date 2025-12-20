"""Service helpers to manage project lifecycle and memberships."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from fastapi.logger import logger
from qdash.datamodel.project import ProjectRole
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.project_membership import ProjectMembershipDocument
from qdash.dbmodel.user import UserDocument


class ProjectService:
    """Encapsulates project and membership creation logic."""

    def create_project(
        self,
        owner_username: str,
        name: str,
        description: str | None = None,
        tags: Iterable[str] | None = None,
        default_role: ProjectRole = ProjectRole.VIEWER,
    ) -> ProjectDocument:
        """Create a project and register owner membership."""
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
        """Ensure the given user has a default project and return it."""
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
