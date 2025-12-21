"""MongoDB implementation of TaskResultHistoryRepository.

This module provides the concrete MongoDB implementation for task result
history persistence operations.
"""

import logging
from datetime import datetime
from typing import Any, Literal, TypedDict

from bunnet import SortDirection
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.task import BaseTaskResultModel
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

logger = logging.getLogger(__name__)


class MetricAggregateResult(TypedDict):
    """Result type for metric aggregation."""

    value: float
    task_id: str | None
    execution_id: str


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

    def aggregate_latest_metrics(
        self,
        *,
        chip_id: str,
        username: str,
        entity_type: Literal["qubit", "coupling"],
        metric_keys: set[str],
        cutoff_time: datetime | None = None,
    ) -> dict[str, dict[str, MetricAggregateResult]]:
        """Aggregate latest metric values for each entity using MongoDB aggregation.

        Uses a single aggregation pipeline to efficiently get the most recent
        value for each (qid, metric) combination. This is much more efficient
        than fetching all documents and filtering in Python.

        Parameters
        ----------
        chip_id : str
            The chip identifier
        username : str
            The username for filtering
        entity_type : Literal["qubit", "coupling"]
            Type of entity to query
        metric_keys : set[str]
            Set of metric keys to extract
        cutoff_time : datetime | None
            Optional datetime for filtering tasks (only include tasks after this time)

        Returns
        -------
        dict[str, dict[str, MetricAggregateResult]]
            Nested dict: metric_name -> entity_id -> {value, task_id, execution_id}

        """
        if not metric_keys:
            return {}

        # Build match stage
        match_stage: dict[str, Any] = {
            "chip_id": chip_id,
            "username": username,
            "task_type": entity_type,
            "status": "completed",
            "$or": [{f"output_parameters.{m}": {"$exists": True}} for m in metric_keys],
        }
        if cutoff_time:
            match_stage["start_at"] = {"$gte": cutoff_time}

        # Aggregation pipeline:
        # 1. Match relevant documents
        # 2. Sort by start_at DESC (most recent first)
        # 3. Convert output_parameters to array
        # 4. Unwind to get one doc per metric
        # 5. Filter to only requested metrics
        # 6. Group by (qid, metric) and take first (latest) value
        pipeline: list[dict[str, Any]] = [
            {"$match": match_stage},
            {"$sort": {"start_at": -1}},
            {
                "$project": {
                    "qid": 1,
                    "execution_id": 1,
                    "task_id": 1,
                    "metrics": {"$objectToArray": "$output_parameters"},
                }
            },
            {"$unwind": "$metrics"},
            {"$match": {"metrics.k": {"$in": list(metric_keys)}}},
            {
                "$group": {
                    "_id": {"qid": "$qid", "metric": "$metrics.k"},
                    "value": {"$first": "$metrics.v.value"},
                    "task_id": {"$first": {"$ifNull": ["$metrics.v.task_id", "$task_id"]}},
                    "execution_id": {"$first": "$execution_id"},
                }
            },
        ]

        results = list(TaskResultHistoryDocument.aggregate(pipeline).run())

        # Transform results to nested dict structure
        metrics_data: dict[str, dict[str, MetricAggregateResult]] = {key: {} for key in metric_keys}

        for doc in results:
            metric_name = doc["_id"]["metric"]
            qid = doc["_id"]["qid"]
            value = doc.get("value")

            if value is not None and isinstance(value, (int, float)):
                metrics_data[metric_name][qid] = MetricAggregateResult(
                    value=float(value),
                    task_id=doc.get("task_id"),
                    execution_id=doc.get("execution_id", ""),
                )

        return metrics_data

    def aggregate_best_metrics(
        self,
        *,
        chip_id: str,
        username: str,
        entity_type: Literal["qubit", "coupling"],
        metric_modes: dict[str, Literal["maximize", "minimize"]],
        cutoff_time: datetime | None = None,
    ) -> dict[str, dict[str, MetricAggregateResult]]:
        """Aggregate best metric values for each entity using MongoDB aggregation.

        Uses aggregation to get the optimal (max or min based on mode) value
        for each (qid, metric) combination.

        Parameters
        ----------
        chip_id : str
            The chip identifier
        username : str
            The username for filtering
        entity_type : Literal["qubit", "coupling"]
            Type of entity to query
        metric_modes : dict[str, Literal["maximize", "minimize"]]
            Dict mapping metric_key -> evaluation mode
        cutoff_time : datetime | None
            Optional datetime for filtering tasks

        Returns
        -------
        dict[str, dict[str, MetricAggregateResult]]
            Nested dict: metric_name -> entity_id -> {value, task_id, execution_id}

        """
        if not metric_modes:
            return {}

        metric_keys = set(metric_modes.keys())

        # Build match stage
        match_stage: dict[str, Any] = {
            "chip_id": chip_id,
            "username": username,
            "task_type": entity_type,
            "status": "completed",
            "$or": [{f"output_parameters.{m}": {"$exists": True}} for m in metric_keys],
        }
        if cutoff_time:
            match_stage["start_at"] = {"$gte": cutoff_time}

        # For best metrics, we need to run separate aggregations for
        # maximize and minimize modes, as MongoDB doesn't support
        # conditional $max/$min in $group easily
        maximize_metrics = {k for k, v in metric_modes.items() if v == "maximize"}
        minimize_metrics = {k for k, v in metric_modes.items() if v == "minimize"}

        metrics_data: dict[str, dict[str, MetricAggregateResult]] = {key: {} for key in metric_keys}

        # Run aggregation for maximize metrics
        if maximize_metrics:
            self._aggregate_best_by_mode(match_stage, maximize_metrics, "max", metrics_data)

        # Run aggregation for minimize metrics
        if minimize_metrics:
            self._aggregate_best_by_mode(match_stage, minimize_metrics, "min", metrics_data)

        return metrics_data

    def _aggregate_best_by_mode(
        self,
        match_stage: dict[str, Any],
        metric_keys: set[str],
        mode: Literal["max", "min"],
        metrics_data: dict[str, dict[str, MetricAggregateResult]],
    ) -> None:
        """Run aggregation for metrics with same optimization mode.

        Parameters
        ----------
        match_stage : dict[str, Any]
            Base match stage for the aggregation
        metric_keys : set[str]
            Set of metric keys to process
        mode : Literal["max", "min"]
            Optimization mode
        metrics_data : dict
            Output dict to populate (mutated in place)

        """
        # Pipeline to get best value per (qid, metric):
        # 1. Match and project
        # 2. Unwind metrics
        # 3. Filter to target metrics
        # 4. Sort by value (DESC for max, ASC for min)
        # 5. Group and take first (which is best)
        sort_direction = -1 if mode == "max" else 1

        pipeline: list[dict[str, Any]] = [
            {"$match": match_stage},
            {
                "$project": {
                    "qid": 1,
                    "execution_id": 1,
                    "task_id": 1,
                    "metrics": {"$objectToArray": "$output_parameters"},
                }
            },
            {"$unwind": "$metrics"},
            {"$match": {"metrics.k": {"$in": list(metric_keys)}}},
            # Filter out null values before sorting
            {"$match": {"metrics.v.value": {"$ne": None}}},
            {"$sort": {"metrics.v.value": sort_direction}},
            {
                "$group": {
                    "_id": {"qid": "$qid", "metric": "$metrics.k"},
                    "value": {"$first": "$metrics.v.value"},
                    "task_id": {"$first": {"$ifNull": ["$metrics.v.task_id", "$task_id"]}},
                    "execution_id": {"$first": "$execution_id"},
                }
            },
        ]

        results = list(TaskResultHistoryDocument.aggregate(pipeline).run())

        for doc in results:
            metric_name = doc["_id"]["metric"]
            qid = doc["_id"]["qid"]
            value = doc.get("value")

            if value is not None and isinstance(value, (int, float)):
                metrics_data[metric_name][qid] = MetricAggregateResult(
                    value=float(value),
                    task_id=doc.get("task_id"),
                    execution_id=doc.get("execution_id", ""),
                )
