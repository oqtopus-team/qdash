"""MongoDB implementation of TaskDefinitionRepository.

This module provides the concrete MongoDB implementation for task definition
data access operations (not to be confused with task results).
"""

import logging
from typing import Any

from qdash.dbmodel.task import TaskDocument

logger = logging.getLogger(__name__)


class MongoTaskDefinitionRepository:
    """MongoDB implementation of TaskDefinitionRepository.

    This repository handles task definitions (templates), not task results.

    Example
    -------
        >>> repo = MongoTaskDefinitionRepository()
        >>> tasks = repo.list_by_project("project-1")

    """

    def list_by_project(self, project_id: str, backend: str | None = None) -> list[dict[str, Any]]:
        """List all task definitions for a project.

        Parameters
        ----------
        project_id : str
            The project identifier
        backend : str | None
            Optional backend name to filter by

        Returns
        -------
        list[dict[str, Any]]
            List of task definition dictionaries

        """
        query: dict[str, Any] = {"project_id": project_id}
        if backend:
            query["backend"] = backend

        tasks = TaskDocument.find(query).run()
        return [
            {
                "name": task.name,
                "description": task.description,
                "task_type": task.task_type,
                "backend": task.backend,
                "input_parameters": task.input_parameters,
                "output_parameters": task.output_parameters,
            }
            for task in tasks
        ]

    def get_task_names(self, username: str) -> list[str]:
        """Get all task names for a user.

        Parameters
        ----------
        username : str
            The username

        Returns
        -------
        list[str]
            List of task names

        """
        tasks = TaskDocument.find({"username": username}).run()
        return [task.name for task in tasks]
