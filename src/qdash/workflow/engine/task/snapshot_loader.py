"""SnapshotParameterLoader - Loads parameters from a previous execution's task results.

This module provides the SnapshotParameterLoader class that fetches task results
from a previous execution and provides input/run parameters for snapshot re-execution.
"""

import logging
from typing import Any

from bunnet import SortDirection

from qdash.datamodel.task_invocation import TaskInvocation
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


DEFAULT_SNAPSHOT_LIMIT = 10_000
"""Maximum number of task result documents to load from a single execution."""


class SnapshotAmbiguityError(ValueError):
    """The source execution has several results the requested call could mean."""


_Record = tuple[TaskInvocation | None, dict[str, Any], dict[str, Any]]


class SnapshotParameterLoader:
    """Loads parameters from a previous execution's task results.

    Loads the exact source task when ``source_task_id`` is available. Full
    workflow re-execution instead loads all records of a source execution and
    matches each new run by task name, qid, and planned call: a call restores the
    record of the same ``step_id`` and ``call_id``, so the coarse and the fine
    ``CheckRamsey`` of one step each get their own inputs back.

    Records written before task calls existed carry no call identity. One such
    record for a (task, qid) is used as before; several are ambiguous, and the
    loader raises :class:`SnapshotAmbiguityError` instead of picking one.

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
        self._cache: dict[tuple[str, str], list[_Record]] | None = None

    @property
    def has_snapshot_source(self) -> bool:
        """Whether this loader represents a re-execution snapshot."""
        return self._source_task_id is not None or self._source_execution_id is not None

    def requires_snapshot(self, task_name: str) -> bool:
        """Whether a task must be resolved from the configured snapshot source."""
        return self.has_snapshot_source and task_name not in self._snapshot_exempt_tasks

    @staticmethod
    def _record(doc: TaskResultHistoryDocument) -> _Record:
        return (doc.invocation, doc.input_parameters or {}, doc.run_parameters or {})

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
                    self._cache[(doc.name, doc.qid)] = [self._record(doc)]
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
                self._cache.setdefault((doc.name, doc.qid), []).append(self._record(doc))

            logger.info(
                "Loaded %d task snapshots from execution %s",
                sum(len(records) for records in self._cache.values()),
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
        self,
        task_name: str,
        qid: str,
        invocation: TaskInvocation | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Get snapshot input/run parameters for a task+qid, and its planned call.

        Parameters
        ----------
        task_name : str
            The task name.
        qid : str
            The qubit ID.
        invocation : TaskInvocation | None
            The planned call being run. Selects the source record of the same
            ``step_id`` and ``call_id`` when the source has call identities.

        Returns
        -------
        tuple[dict[str, Any], dict[str, Any]] | None
            Tuple of (input_parameters, run_parameters), or None if not found.

        Raises
        ------
        SnapshotAmbiguityError
            When several source records match and none identifies the call.

        """
        if task_name in self._snapshot_exempt_tasks:
            return None
        self._load()
        assert self._cache is not None
        records = self._cache.get((task_name, qid), [])
        if not records:
            return None
        if self._source_task_id is not None:
            # Single-task re-execution restores exactly the requested task result.
            _, inputs, run = records[0]
            return inputs, run

        identified = [record for record in records if record[0] is not None]
        if invocation is not None and identified:
            matches = [
                record
                for record in identified
                if record[0] is not None
                and record[0].call_id == invocation.call_id
                and record[0].step_id == invocation.step_id
            ]
            if not matches:
                return None
            # The same call ran once per target in an execution; a later record
            # of it can only be the same call recorded again.
            _, inputs, run = matches[-1]
            return inputs, run

        if len(records) == 1:
            _, inputs, run = records[0]
            return inputs, run
        raise SnapshotAmbiguityError(
            f"Source execution {self._source_execution_id} ran task {task_name!r} on qid "
            f"{qid!r} {len(records)} times"
            + (
                " without call identities"
                if not identified
                else ", and this run has no call identity to choose one by"
            )
            + "; re-run a single task result by task_id instead"
        )
