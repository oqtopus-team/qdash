"""MongoDB implementation of ExecutionLockRepository.

This module provides the concrete MongoDB implementation for execution
lock operations.
"""

import logging

from qdash.common.execution_resources import ExecutionResourceScope, scopes_conflict
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

    def has_conflict(self, project_id: str, scope: ExecutionResourceScope) -> bool:
        """Inspect current claims without acquiring a lock or creating a record."""
        doc = ExecutionLockDocument.find_one({"project_id": project_id}).run()
        if doc is None:
            return False
        if not doc.claims:
            return doc.locked
        return any(
            scopes_conflict(
                scope,
                ExecutionResourceScope(claim.chip_id, tuple(claim.resources), claim.exclusive),
            )
            for claim in doc.claims
        )

    def try_lock(
        self,
        project_id: str,
        execution_id: str | None = None,
        chip_id: str = "",
        resources: tuple[str, ...] = (),
        exclusive: bool = True,
    ) -> bool:
        """Atomically acquire the execution lock, unless another execution holds it.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str | None
            The execution that will own the lock

        Returns
        -------
        bool
            True when the lock was acquired or already owned, False when held

        """
        return ExecutionLockDocument.try_lock(
            project_id=project_id,
            execution_id=execution_id,
            chip_id=chip_id,
            resources=resources,
            exclusive=exclusive,
        )

    def lock(self, project_id: str, execution_id: str | None = None) -> None:
        """Acquire the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str | None
            The execution that owns the lock, if known

        """
        ExecutionLockDocument.lock(project_id=project_id, execution_id=execution_id)

    def unlock(self, project_id: str, execution_id: str | None = None) -> None:
        """Release the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        ExecutionLockDocument.unlock(project_id=project_id, execution_id=execution_id)
