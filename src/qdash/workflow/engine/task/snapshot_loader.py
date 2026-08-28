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
    parameter_overrides : dict[str, dict[str, Any]] | None
        Optional user overrides. Shape: ``{"run": {...}, "input": {...}}``.
        Values are merged on top of snapshot parameters.
    limit : int
        Maximum number of task result documents to load. Defaults to
        ``DEFAULT_SNAPSHOT_LIMIT`` (10 000).

    """

    def __init__(
        self,
        source_execution_id: str | None,
        project_id: str,
        source_task_id: str | None = None,
        parameter_overrides: dict[str, dict[str, Any]] | None = None,
        snapshot_exempt_tasks: set[str] | None = None,
        limit: int = DEFAULT_SNAPSHOT_LIMIT,
    ) -> None:
        self._source_execution_id = source_execution_id
        self._project_id = project_id
        self._source_task_id = source_task_id
        self._parameter_overrides = parameter_overrides
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
        self._load()
        assert self._cache is not None
        result = self._cache.get((task_name, qid))
        if result is None:
            return None
        if not self._parameter_overrides:
            return result
        snap_input, snap_run = result
        merged_input = self._merge_overrides(snap_input, self._parameter_overrides.get("input", {}))
        merged_run = self._merge_overrides(snap_run, self._parameter_overrides.get("run", {}))
        return merged_input, merged_run

    @staticmethod
    def _merge_overrides(
        snapshot_dict: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge user overrides on top of snapshot parameters.

        For each key in *overrides*, if the snapshot entry is a dict with a
        ``"value"`` key the override replaces only the ``"value"`` field
        (preserving ``unit``, ``value_type``, ``description``, etc.).
        Otherwise the entry is replaced entirely.
        """
        if not overrides:
            return snapshot_dict
        merged = {**snapshot_dict}
        for key, new_value in overrides.items():
            existing = merged.get(key)
            if isinstance(existing, dict) and "value" in existing:
                merged[key] = {**existing, "value": new_value}
            else:
                merged[key] = new_value
        return merged
