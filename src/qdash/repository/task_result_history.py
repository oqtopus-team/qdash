"""MongoDB implementation of TaskResultHistoryRepository.

This module provides the concrete MongoDB implementation for task result
history persistence operations.
"""

import logging
from typing import Any

from bunnet import SortDirection

from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.task import BaseTaskResultModel
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


class MongoTaskResultHistoryRepository:
    """MongoDB implementation of TaskResultHistoryRepository.

    This class encapsulates all MongoDB-specific logic for task result
    history persistence.

    Example
    -------
        >>> repo = MongoTaskResultHistoryRepository()
        >>> results = repo.find_latest_by_chip_and_qids(
        ...     project_id="proj-1",
        ...     chip_id="64Qv3",
        ...     qids=["0", "1", "2", "3"],
        ...     task_names=["CheckRabi", "CheckT1"],
        ... )

    """

    def save(self, task: BaseTaskResultModel, execution_model: ExecutionModel) -> None:
        """Save a task result to the history.

        Parameters
        ----------
        task : BaseTaskResultModel
            The task result to save
        execution_model : ExecutionModel
            The parent execution context

        """
        TaskResultHistoryDocument.upsert_document(
            task=task,
            execution_model=execution_model,
        )

    def find_latest_by_chip_and_qids(
        self,
        *,
        project_id: str,
        chip_id: str,
        qids: list[str],
        task_names: list[str],
    ) -> list[TaskResultHistoryDocument]:
        """Find the latest task results for specified qubits and tasks.

        Parameters
        ----------
        project_id : str
            The project identifier
        chip_id : str
            The chip identifier
        qids : list[str]
            List of qubit identifiers
        task_names : list[str]
            List of task names to filter

        Returns
        -------
        list[TaskResultHistoryDocument]
            List of task result documents, sorted by end_at descending

        """
        results: list[TaskResultHistoryDocument] = (
            TaskResultHistoryDocument.find(
                {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "qid": {"$in": qids},
                    "name": {"$in": task_names},
                }
            )
            .sort([("end_at", SortDirection.DESCENDING)])
            .run()
        )
        return results

    def find(
        self,
        query: dict[str, Any],
        sort: list[tuple[str, SortDirection]] | None = None,
        limit: int | None = None,
    ) -> list[TaskResultHistoryDocument]:
        """Find task results by query.

        Parameters
        ----------
        query : dict[str, Any]
            MongoDB query dict
        sort : list[tuple[str, SortDirection]] | None
            Optional sort specification
        limit : int | None
            Optional limit

        Returns
        -------
        list[TaskResultHistoryDocument]
            List of matching documents

        """
        finder = TaskResultHistoryDocument.find(query)
        if sort:
            finder = finder.sort(sort)
        if limit:
            finder = finder.limit(limit)
        return list(finder.run())

    def find_with_projection(
        self,
        query: dict[str, Any],
        projection_model: type[Any],
        sort: list[tuple[str, SortDirection]] | None = None,
    ) -> list[Any]:
        """Find task results with a projection.

        Parameters
        ----------
        query : dict[str, Any]
            MongoDB query dict
        projection_model : type[Any]
            The projection model class to use
        sort : list[tuple[str, SortDirection]] | None
            Optional sort specification

        Returns
        -------
        list[Any]
            List of projected documents

        """
        finder = TaskResultHistoryDocument.find(query)
        if sort:
            finder = finder.sort(sort)
        return list(finder.project(projection_model).run())
