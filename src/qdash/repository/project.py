"""Project repository implementation."""

from typing import Any

from qdash.datamodel.project import ProjectRole
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.project import ProjectDocument


class MongoProjectRepository:
    """MongoDB implementation of Project repository."""

    def find_by_id(self, project_id: str) -> ProjectDocument | None:
        """Find project by project ID.

        Args:
            project_id: Project identifier

        Returns:
            ProjectDocument if found, None otherwise
        """
        return ProjectDocument.find_by_id(project_id)  # type: ignore[no-any-return]

    def find_one(self, query: dict[str, Any]) -> ProjectDocument | None:
        """Find a single project document by query.

        Args:
            query: MongoDB query dict

        Returns:
            ProjectDocument if found, None otherwise
        """
        return ProjectDocument.find_one(query).run()

    def find(self, query: dict[str, Any]) -> list[ProjectDocument]:
        """Find projects by query.

        Args:
            query: MongoDB query dict

        Returns:
            List of ProjectDocument objects
        """
        return list(ProjectDocument.find(query).run())

    def insert(self, project: ProjectDocument) -> None:
        """Insert a new project document.

        Args:
            project: Project document to insert
        """
        project.insert()

    def save(self, project: ProjectDocument) -> None:
        """Save (update) an existing project document.

        Args:
            project: Project document to save
        """
        project.save()

    def delete(self, project: ProjectDocument) -> None:
        """Delete a project document.

        Args:
            project: Project document to delete
        """
        project.delete()

    def create_project(
        self,
        owner_username: str,
        name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        default_role: ProjectRole = ProjectRole.VIEWER,
    ) -> ProjectDocument:
        """Create a new project.

        Args:
            owner_username: Owner username
            name: Project display name
            description: Project description
            tags: Project tags
            default_role: Default role for invite links

        Returns:
            Created ProjectDocument
        """
        project = ProjectDocument(
            owner_username=owner_username,
            name=name,
            description=description,
            tags=tags or [],
            default_role=default_role,
            system_info=SystemInfoModel(),
        )
        project.insert()
        return project
