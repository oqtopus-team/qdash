"""SnapshotParameterLoader - Loads parameters from a previous execution's task results.

This module provides the SnapshotParameterLoader class that fetches task results
from a previous execution and provides input/run parameters for snapshot re-execution.
"""

import logging
from typing import Any

from bunnet import SortDirection

from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


DEFAULT_SNAPSHOT_LIMIT = 10_000
"""Maximum number of task result documents to load from a single execution."""


class SnapshotParameterLoader:
    """Loads parameters from a previous execution's task results.

    Loads the exact source task when ``source_task_id`` is available. Full
    workflow re-execution may instead load all records for a source execution
    and index them by (task_name, qid).

    Parameters
    ----------
    source_execution_id : str
        The execution ID to load snapshot parameters from.
    project_id : str
        The project identifier.
    source_task_id : str | None
        Exact task result ID to load for single-task re-execution.
    limit : int
        Maximum number of task result documents to load. Defaults to
        ``DEFAULT_SNAPSHOT_LIMIT`` (10 000).

    """

    def __init__(
        self,
        source_execution_id: str | None,
        project_id: str,
        source_task_id: str | None = None,
        snapshot_exempt_tasks: set[str] | None = None,
        limit: int = DEFAULT_SNAPSHOT_LIMIT,
    ) -> None:
        self._source_execution_id = source_execution_id
        self._project_id = project_id
        self._source_task_id = source_task_id
        self._snapshot_exempt_tasks = snapshot_exempt_tasks or set()
        self._limit = limit
        self._cache: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] | None = None

    @property
    def has_snapshot_source(self) -> bool:
        """Whether this loader represents a re-execution snapshot."""
        return self._source_task_id is not None or self._source_execution_id is not None

    def requires_snapshot(self, task_name: str) -> bool:
        """Whether a task must be resolved from the configured snapshot source."""
        return self.has_snapshot_source and task_name not in self._snapshot_exempt_tasks

    def _load(self) -> None:
        """Lazily load all task results for the source execution."""
        if self._cache is not None:
            return
        if self._source_task_id is None and self._source_execution_id is None:
            self._cache = {}
            return

        self._cache = {}
        try:
            if self._source_task_id is not None:
                doc = TaskResultHistoryDocument.find_one(
                    {
                        "project_id": self._project_id,
                        "task_id": self._source_task_id,
                    }
                ).run()
                if doc is not None:
                    self._cache[(doc.name, doc.qid)] = (
                        doc.input_parameters or {},
                        doc.run_parameters or {},
                    )
                return

            assert self._source_execution_id is not None
            docs: list[TaskResultHistoryDocument] = (
                TaskResultHistoryDocument.find(
                    {
                        "project_id": self._project_id,
                        "execution_id": self._source_execution_id,
                    }
                )
                .sort([("start_at", SortDirection.ASCENDING)])
                .limit(self._limit)
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
        if task_name in self._snapshot_exempt_tasks:
            return None
        self._load()
        assert self._cache is not None
        return self._cache.get((task_name, qid))
