"""Project membership repository implementation."""

from typing import Any

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project_membership import ProjectMembershipDocument


class MongoProjectMembershipRepository:
    """MongoDB implementation of Project Membership repository."""

    def get_active_membership(
        self, project_id: str, username: str, user_id: str | None = None
    ) -> ProjectMembershipDocument | None:
        """Fetch active membership for the user/project pair.

        Args:
            project_id: Project identifier
            username: Member username

        Returns:
            ProjectMembershipDocument if found, None otherwise
        """
        return ProjectMembershipDocument.get_active_membership(project_id, username, user_id)  # type: ignore[no-any-return]

    def find_one(self, query: dict[str, Any]) -> ProjectMembershipDocument | None:
        """Find a single membership document by query.

        Args:
            query: MongoDB query dict

        Returns:
            ProjectMembershipDocument if found, None otherwise
        """
        return ProjectMembershipDocument.find_one(query).run()

    def find(self, query: dict[str, Any]) -> list[ProjectMembershipDocument]:
        """Find memberships by query.

        Args:
            query: MongoDB query dict

        Returns:
            List of ProjectMembershipDocument objects
        """
        return list(ProjectMembershipDocument.find(query).run())

    def find_by_user(
        self, user_id: str | None, status: str = "active"
    ) -> list[ProjectMembershipDocument]:
        """Find all memberships for a user."""
        if not user_id:
            return []
        query: dict[str, Any] = {"user_id": user_id, "status": status}
        return list(ProjectMembershipDocument.find(query).run())

    def find_by_project(self, project_id: str) -> list[ProjectMembershipDocument]:
        """Find all memberships for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of ProjectMembershipDocument objects
        """
        return list(ProjectMembershipDocument.find({"project_id": project_id}).run())

    def delete_by_project(self, project_id: str) -> None:
        """Delete all memberships for a project.

        Args:
            project_id: Project identifier
        """
        ProjectMembershipDocument.find({"project_id": project_id}).delete().run()

    def insert(self, membership: ProjectMembershipDocument) -> None:
        """Insert a new membership document.

        Args:
            membership: Membership document to insert
        """
        membership.insert()

    def save(self, membership: ProjectMembershipDocument) -> None:
        """Save (update) an existing membership document.

        Args:
            membership: Membership document to save
        """
        membership.save()

    def create_membership(
        self,
        project_id: str,
        user_id: str | None,
        username: str,
        role: ProjectRole,
        status: str = "active",
        invited_by_user_id: str | None = None,
        invited_by: str | None = None,
    ) -> ProjectMembershipDocument:
        """Create a new project membership.

        Args:
            project_id: Project identifier
            username: Member username
            role: Assigned project role
            status: Invitation status
            invited_by: Inviter username

        Returns:
            Created ProjectMembershipDocument
        """
        membership = ProjectMembershipDocument(
            project_id=project_id,
            user_id=user_id,
            username=username,
            role=role,
            status=status,
            invited_by_user_id=invited_by_user_id,
            invited_by=invited_by,
            system_info=SystemInfoModel(),
        )
        membership.insert()
        return membership
