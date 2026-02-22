"""Metrics service for QDash API.

This module provides business logic for chip calibration metrics,
abstracting away the repository layer and aggregation logic from the routers.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Literal

from fastapi import HTTPException
from qdash.api.lib.metrics_config import load_metrics_config
from qdash.api.schemas.metrics import MetricValue
from qdash.common.datetime_utils import now

if TYPE_CHECKING:
    from qdash.repository.protocols import TaskResultHistoryRepository

logger = logging.getLogger(__name__)


class MetricsService:
    """Service for chip calibration metrics operations."""

    def __init__(self, task_result_repository: TaskResultHistoryRepository) -> None:
        self._task_result_repo = task_result_repository

    def extract_entity_metrics(
        self,
        chip_id: str,
        project_id: str,
        entity_type: Literal["qubit", "coupling"],
        within_hours: int | None = None,
        selection_mode: Literal["latest", "best", "average"] = "latest",
    ) -> dict[str, dict[str, MetricValue]]:
        """Extract metrics for qubits or couplings from task result history.

        Args:
        ----
            chip_id: The chip identifier
            project_id: The project identifier for filtering
            entity_type: "qubit" or "coupling"
            within_hours: Optional time filter in hours
            selection_mode: "latest", "best", or "average"

        Returns:
        -------
            Dictionary mapping metric_name -> entity_id -> MetricValue

        """
        config = load_metrics_config()
        entity_metrics = config.qubit_metrics if entity_type == "qubit" else config.coupling_metrics
        valid_metric_keys = set(entity_metrics.keys())

        cutoff_time = None
        if within_hours:
            cutoff_time = now() - timedelta(hours=within_hours)

        return self._extract_metrics(
            chip_id=chip_id,
            project_id=project_id,
            entity_type=entity_type,
            valid_metric_keys=valid_metric_keys,
            selection_mode=selection_mode,
            cutoff_time=cutoff_time,
            metrics_config=entity_metrics if selection_mode == "best" else None,
        )

    def _extract_metrics(
        self,
        chip_id: str,
        project_id: str,
        entity_type: Literal["qubit", "coupling"],
        valid_metric_keys: set[str],
        selection_mode: Literal["latest", "best", "average"],
        cutoff_time: Any | None,
        metrics_config: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, MetricValue]]:
        """Extract metrics using the appropriate aggregation strategy."""
        if not valid_metric_keys:
            return {key: {} for key in valid_metric_keys}

        try:
            if selection_mode == "best":
                metric_modes: dict[str, Literal["maximize", "minimize"]] = {}
                if metrics_config:
                    for key in valid_metric_keys:
                        mode = metrics_config[key].evaluation.mode
                        if mode in ("maximize", "minimize"):
                            metric_modes[key] = mode
                if not metric_modes:
                    return {key: {} for key in valid_metric_keys}
                agg_results = self._task_result_repo.aggregate_best_metrics(
                    chip_id=chip_id,
                    project_id=project_id,
                    entity_type=entity_type,
                    metric_modes=metric_modes,
                    cutoff_time=cutoff_time,
                )
            elif selection_mode == "average":
                agg_results = self._task_result_repo.aggregate_average_metrics(
                    chip_id=chip_id,
                    project_id=project_id,
                    entity_type=entity_type,
                    metric_keys=valid_metric_keys,
                    cutoff_time=cutoff_time,
                )
            else:  # latest
                agg_results = self._task_result_repo.aggregate_latest_metrics(
                    chip_id=chip_id,
                    project_id=project_id,
                    entity_type=entity_type,
                    metric_keys=valid_metric_keys,
                    cutoff_time=cutoff_time,
                )
        except Exception as e:
            logger.error(f"Failed to aggregate {selection_mode} metrics: {e}")
            raise HTTPException(status_code=500, detail=f"Database query failed: {e}") from e

        metrics_data: dict[str, dict[str, MetricValue]] = {key: {} for key in valid_metric_keys}
        for metric_name, entity_values in agg_results.items():
            for entity_id, result in entity_values.items():
                metrics_data[metric_name][entity_id] = MetricValue(
                    value=result["value"],
                    task_id=result["task_id"],
                    execution_id=result["execution_id"],
                    stddev=result.get("stddev"),
                )

        return metrics_data
