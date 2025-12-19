"""MongoDB implementations for CalibService repositories.

This module provides MongoDB implementations for:
- ExecutionCounterRepository: Atomic counter for execution IDs
- ExecutionLockRepository: Mutual exclusion for calibration sessions
- UserRepository: User data access
- TaskRepository: Task definition access
"""

import logging

from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)


class MongoExecutionCounterRepository:
    """MongoDB implementation of ExecutionCounterRepository.

    This class delegates to ExecutionCounterDocument for atomic counter operations.

    Example
    -------
        >>> repo = MongoExecutionCounterRepository()
        >>> index = repo.get_next_index(
        ...     date="20240115",
        ...     username="alice",
        ...     chip_id="64Qv3",
        ...     project_id="proj-1"
        ... )

    """

    def get_next_index(
        self,
        date: str,
        username: str,
        chip_id: str,
        project_id: str,
    ) -> int:
        """Get the next execution index atomically.

        Parameters
        ----------
        date : str
            The date string (e.g., "20240115")
        username : str
            The username
        chip_id : str
            The chip identifier
        project_id : str
            The project identifier

        Returns
        -------
        int
            The next index (0 on first call, then 1, 2, 3...)

        """
        return int(
            ExecutionCounterDocument.get_next_index(
                date=date,
                username=username,
                chip_id=chip_id,
                project_id=project_id,
            )
        )


class MongoExecutionLockRepository:
    """MongoDB implementation of ExecutionLockRepository.

    This class delegates to ExecutionLockDocument for lock operations.

    Example
    -------
        >>> repo = MongoExecutionLockRepository()
        >>> if not repo.is_locked(project_id="proj-1"):
        ...     repo.lock(project_id="proj-1")

    """

    def is_locked(self, project_id: str) -> bool:
        """Check if the project is currently locked.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        bool
            True if locked, False otherwise

        """
        return bool(ExecutionLockDocument.get_lock_status(project_id=project_id))

    def lock(self, project_id: str) -> None:
        """Acquire the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        ExecutionLockDocument.lock(project_id=project_id)

    def unlock(self, project_id: str) -> None:
        """Release the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        ExecutionLockDocument.unlock(project_id=project_id)


class MongoUserRepository:
    """MongoDB implementation of UserRepository.

    This class delegates to UserDocument for user data access.

    Example
    -------
        >>> repo = MongoUserRepository()
        >>> project_id = repo.get_default_project_id(username="alice")

    """

    def get_default_project_id(self, username: str) -> str | None:
        """Get the user's default project ID.

        Parameters
        ----------
        username : str
            The username to look up

        Returns
        -------
        str | None
            The default project ID, or None if not set or user not found

        """
        user = UserDocument.find_one({"username": username}).run()
        if user is None:
            return None
        # default_project_id is str | None
        default_project_id: str | None = user.default_project_id
        return default_project_id


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
