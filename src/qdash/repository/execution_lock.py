"""MongoDB implementation of ExecutionLockRepository.

This module provides the concrete MongoDB implementation for execution
lock operations.
"""

import logging

from qdash.dbmodel.execution_lock import ExecutionLockDocument

logger = logging.getLogger(__name__)


class MongoExecutionLockRepository:
    """MongoDB implementation of ExecutionLockRepository.

    This class provides mutual exclusion for calibration sessions.
    Only one calibration can run per project at a time.

    Example
    -------
        >>> repo = MongoExecutionLockRepository()
        >>> if not repo.is_locked(project_id="proj-1"):
        ...     repo.lock(project_id="proj-1")
        ...     try:
        ...         # run calibration
        ...     finally:
        ...         repo.unlock(project_id="proj-1")

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
        status = ExecutionLockDocument.get_lock_status(project_id=project_id)
        return status is True

    def get_lock_status(self, project_id: str) -> bool | None:
        """Get the raw lock status.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        bool | None
            True if locked, False if unlocked, None if no lock record exists

        """
        result: bool | None = ExecutionLockDocument.get_lock_status(project_id=project_id)
        return result

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
