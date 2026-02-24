"""SnapshotParameterLoader - Loads parameters from a previous execution's task results.

This module provides the SnapshotParameterLoader class that fetches task results
from a previous execution and provides input/run parameters for snapshot re-execution.
"""

import logging
from typing import Any

from bunnet import SortDirection
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


class SnapshotParameterLoader:
    """Loads parameters from a previous execution's task results.

    Lazily loads all TaskResultHistoryDocument records for the source execution
    and caches them by (task_name, qid) key. Provides a get_snapshot() method
    that returns input_parameters and run_parameters for a given task+qid.

    Parameters
    ----------
    source_execution_id : str
        The execution ID to load snapshot parameters from.
    project_id : str
        The project identifier.

    """

    def __init__(self, source_execution_id: str, project_id: str) -> None:
        self._source_execution_id = source_execution_id
        self._project_id = project_id
        self._cache: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] | None = None

    def _load(self) -> None:
        """Lazily load all task results for the source execution."""
        if self._cache is not None:
            return

        self._cache = {}
        try:
            docs: list[TaskResultHistoryDocument] = (
                TaskResultHistoryDocument.find(
                    {
                        "project_id": self._project_id,
                        "execution_id": self._source_execution_id,
                    }
                )
                .sort([("start_at", SortDirection.ASCENDING)])
                .run()
            )

            for doc in docs:
                key = (doc.name, doc.qid)
                self._cache[key] = (
                    doc.input_parameters or {},
                    doc.run_parameters or {},
                )

            logger.info(
                "Loaded %d task snapshots from execution %s",
                len(self._cache),
                self._source_execution_id,
            )
        except Exception:
            logger.warning(
                "Failed to load snapshots from execution %s",
                self._source_execution_id,
                exc_info=True,
            )
            self._cache = {}

    def get_snapshot(
        self, task_name: str, qid: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Get snapshot input/run parameters for a task+qid.

        Parameters
        ----------
        task_name : str
            The task name.
        qid : str
            The qubit ID.

        Returns
        -------
        tuple[dict[str, Any], dict[str, Any]] | None
            Tuple of (input_parameters, run_parameters), or None if not found.

        """
        self._load()
        assert self._cache is not None
        return self._cache.get((task_name, qid))
