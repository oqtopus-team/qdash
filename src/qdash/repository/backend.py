"""MongoDB implementation of BackendRepository.

This module provides the concrete MongoDB implementation for backend
data access operations.
"""

import logging
from typing import Any

from qdash.dbmodel.backend import BackendDocument

logger = logging.getLogger(__name__)


class MongoBackendRepository:
    """MongoDB implementation of BackendRepository.

    Example
    -------
        >>> repo = MongoBackendRepository()
        >>> backends = repo.list_by_project("project-1")

    """

    def list_by_project(self, project_id: str) -> list[dict[str, Any]]:
        """List all backends for a project.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        list[dict[str, Any]]
            List of backend dictionaries

        """
        backends = BackendDocument.find({"project_id": project_id}).to_list()
        return [backend.dict() for backend in backends]
