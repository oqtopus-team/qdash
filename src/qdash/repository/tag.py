"""MongoDB implementation of TagRepository.

This module provides the concrete MongoDB implementation for tag
data access operations.
"""

import logging

from qdash.dbmodel.tag import TagDocument

logger = logging.getLogger(__name__)


class MongoTagRepository:
    """MongoDB implementation of TagRepository.

    Example
    -------
        >>> repo = MongoTagRepository()
        >>> tags = repo.list_by_project("project-1")

    """

    def list_by_project(self, project_id: str) -> list[str]:
        """List all tag names for a project.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        list[str]
            List of tag names

        """
        tags = TagDocument.find({"project_id": project_id}).run()
        return [tag.name for tag in tags]

    def insert_tags(self, tags: list[str], username: str, project_id: str) -> None:
        """Insert tags if they don't exist.

        Parameters
        ----------
        tags : list[str]
            List of tag names to insert
        username : str
            The username
        project_id : str
            The project identifier

        """
        TagDocument.insert_tags(tags, username, project_id)
