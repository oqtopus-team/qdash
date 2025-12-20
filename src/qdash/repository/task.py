"""MongoDB implementation of TaskRepository.

This module provides the concrete MongoDB implementation for task
definition access operations.
"""

import logging

from qdash.dbmodel.task import TaskDocument

logger = logging.getLogger(__name__)


class MongoTaskRepository:
    """MongoDB implementation of TaskRepository.

    This class delegates to TaskDocument for task definition queries.

    Example
    -------
        >>> repo = MongoTaskRepository()
        >>> names = repo.get_task_names(username="alice")
        >>> if "CheckFreq" in names:
        ...     print("Task is valid")

    """

    def get_task_names(self, username: str) -> list[str]:
        """Get all task names available for a user.

        Parameters
        ----------
        username : str
            The username to look up tasks for

        Returns
        -------
        list[str]
            List of available task names

        """
        tasks = TaskDocument.find({"username": username}).run()
        return [task.name for task in tasks]
