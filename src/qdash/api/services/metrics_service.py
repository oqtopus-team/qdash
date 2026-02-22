"""Metrics service for QDash API.

This module provides business logic for chip calibration metrics,
abstracting away the repository layer and aggregation logic from the routers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from bunnet import SortDirection
from fastapi import HTTPException
from qdash.api.lib.metrics_config import load_metrics_config
from qdash.api.schemas.metrics import (
    ChipMetricsResponse,
    MetricHistoryItem,
    MetricValue,
    QubitMetricHistoryResponse,
)
from qdash.common.datetime_utils import now, to_datetime

if TYPE_CHECKING:
    from io import BytesIO

    from qdash.repository.protocols import ChipRepository, TaskResultHistoryRepository

logger = logging.getLogger(__name__)


def normalize_qid(qid: str) -> str:
    """Normalize qubit ID to canonical format.

    Removes "Q" prefix and leading zeros, handling edge cases.

    Args:
    ----
        qid: Qubit ID in any format (e.g., "0", "Q00", "Q01", "1")

    Returns:
    -------
        Normalized qubit ID without prefix or leading zeros (e.g., "0", "1")

    Examples:
    --------
        >>> normalize_qid("Q00")
        "0"
        >>> normalize_qid("Q01")
        "1"
        >>> normalize_qid("10")
        "10"

    """
    return qid.replace("Q", "").lstrip("0") or "0"


def _extract_metric_output_info(
    metric_data: Any,
) -> tuple[float | int | None, datetime | None, str | None]:
    """Extract value, calibrated_at, and task_id from metric output data."""

    if metric_data is None:
        return None, None, None

    def _parse_calibrated_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return to_datetime(value)
        return None

    if isinstance(metric_data, dict):
        return (
            metric_data.get("value"),
            _parse_calibrated_at(metric_data.get("calibrated_at")),
            metric_data.get("task_id"),
        )

    if hasattr(metric_data, "model_dump"):
        data = metric_data.model_dump()
        return (
            data.get("value"),
            _parse_calibrated_at(data.get("calibrated_at")),
            data.get("task_id"),
        )

    if hasattr(metric_data, "value"):
        return (
            getattr(metric_data, "value", None),
            _parse_calibrated_at(getattr(metric_data, "calibrated_at", None)),
            getattr(metric_data, "task_id", None),
        )

    return metric_data, None, None


def _get_task_timestamp(task_doc: Any) -> datetime:
    """Get the best available timestamp for a task history document."""

    timestamp = getattr(task_doc, "start_at", None) or getattr(task_doc, "end_at", None)
    if timestamp is not None:
        if isinstance(timestamp, datetime):
            return timestamp
        parsed = to_datetime(timestamp)
        if parsed is not None:
            return parsed

    system_info = getattr(task_doc, "system_info", None)
    if isinstance(system_info, dict):
        created_at = system_info.get("created_at")
        if created_at is not None:
            if isinstance(created_at, datetime):
                return created_at
            parsed = to_datetime(str(created_at))
            if parsed is not None:
                return parsed
        return now()

    if system_info is not None:
        created_at = getattr(system_info, "created_at", None)
        if created_at is not None:
            if isinstance(created_at, datetime):
                return created_at
            parsed = to_datetime(str(created_at))
            if parsed is not None:
                return parsed

    return now()


class MetricsService:
    """Service for chip calibration metrics operations."""

    def __init__(
        self,
        task_result_repository: TaskResultHistoryRepository,
        chip_repository: ChipRepository,
    ) -> None:
        self._task_result_repo = task_result_repository
        self._chip_repo = chip_repository

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

    def get_chip_metrics(
        self,
        chip_id: str,
        project_id: str,
        username: str,
        within_hours: int | None = None,
        selection_mode: Literal["latest", "best", "average"] = "latest",
    ) -> ChipMetricsResponse:
        """Get chip calibration metrics for visualization.

        Args:
        ----
            chip_id: The chip identifier
            project_id: The project identifier
            username: The requesting user's name
            within_hours: Optional time filter
            selection_mode: Selection strategy

        Returns:
        -------
            ChipMetricsResponse with all metrics data

        Raises:
        ------
            HTTPException: 404 if chip not found

        """
        qubit_count = self._chip_repo.get_qubit_count(project_id, chip_id)
        if qubit_count == 0:
            chip = self._chip_repo.find_one_document({"project_id": project_id, "chip_id": chip_id})
            if not chip:
                raise HTTPException(
                    status_code=404,
                    detail=f"Chip {chip_id} not found in project {project_id}",
                )

        qubit_metrics = self.extract_entity_metrics(
            chip_id, project_id, "qubit", within_hours, selection_mode
        )
        coupling_metrics = self.extract_entity_metrics(
            chip_id, project_id, "coupling", within_hours, selection_mode
        )

        return ChipMetricsResponse(
            chip_id=chip_id,
            username=username,
            qubit_count=qubit_count,
            within_hours=within_hours,
            qubit_metrics=qubit_metrics,
            coupling_metrics=coupling_metrics,
        )

    def get_metric_history(
        self,
        chip_id: str,
        qid: str,
        project_id: str,
        username: str,
        metric: str,
        entity_type: Literal["qubit", "coupling"],
        limit: int | None = None,
        within_days: int | None = 30,
    ) -> QubitMetricHistoryResponse:
        """Get historical metric data for a specific qubit or coupling.

        Args:
        ----
            chip_id: The chip identifier
            qid: The qubit or coupling identifier
            project_id: The project identifier
            username: The requesting user's name
            metric: Metric name to retrieve history for
            entity_type: "qubit" or "coupling"
            limit: Maximum number of history items
            within_days: Optional filter to last N days

        Returns:
        -------
            QubitMetricHistoryResponse with historical metric data

        """
        cutoff_time = None
        if within_days:
            cutoff_time = now() - timedelta(days=within_days)

        query: dict[str, Any] = {
            "project_id": project_id,
            "chip_id": chip_id,
            "task_type": entity_type,
            f"output_parameters.{metric}": {"$exists": True},
        }

        if entity_type == "qubit":
            normalized_qid = normalize_qid(qid)
            qid_variants = list(
                {normalized_qid, qid, f"Q{normalized_qid.zfill(2)}", f"Q{normalized_qid.zfill(3)}"}
            )
            query["qid"] = {"$in": qid_variants}
        else:
            query["qid"] = qid

        if cutoff_time:
            query["start_at"] = {"$gte": cutoff_time}

        task_results = self._task_result_repo.find(
            query, sort=[("start_at", SortDirection.DESCENDING)], limit=limit
        )

        history_items: list[MetricHistoryItem] = []

        for task_doc in task_results:
            metric_data = task_doc.output_parameters.get(metric)
            value, calibrated_at, metric_task_id = _extract_metric_output_info(metric_data)

            if value is None:
                continue

            history_items.append(
                MetricHistoryItem(
                    value=value,
                    execution_id=task_doc.execution_id,
                    task_id=metric_task_id or task_doc.task_id,
                    timestamp=_get_task_timestamp(task_doc),
                    calibrated_at=calibrated_at,
                    name=task_doc.name,
                    input_parameters=task_doc.input_parameters or None,
                    output_parameters=task_doc.output_parameters or None,
                )
            )

        if not history_items:
            logger.warning(
                "No task history found for project=%s, chip=%s, qid=%s, metric=%s",
                project_id,
                chip_id,
                qid,
                metric,
            )

        return QubitMetricHistoryResponse(
            chip_id=chip_id,
            qid=qid,
            metric_name=metric,
            username=username,
            history=history_items,
        )

    def generate_metrics_pdf(
        self,
        chip_id: str,
        project_id: str,
        username: str,
        within_hours: int | None = None,
        selection_mode: Literal["latest", "best", "average"] = "latest",
    ) -> tuple[BytesIO, str, str]:
        """Generate a PDF report for chip metrics.

        Args:
        ----
            chip_id: The chip identifier
            project_id: The project identifier
            username: The requesting user's name
            within_hours: Optional time filter
            selection_mode: Selection strategy

        Returns:
        -------
            Tuple of (pdf_buffer, filename, topology_id)

        Raises:
        ------
            HTTPException: 404 if chip not found, 500 if PDF generation fails

        """
        from qdash.api.lib.metrics_pdf import MetricsPDFGenerator

        chip = self._chip_repo.find_one_document({"project_id": project_id, "chip_id": chip_id})
        if not chip:
            raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")

        qubit_count = self._chip_repo.get_qubit_count(project_id, chip_id)

        qubit_metrics_data = self.extract_entity_metrics(
            chip_id, project_id, "qubit", within_hours, selection_mode
        )
        coupling_metrics_data = self.extract_entity_metrics(
            chip_id, project_id, "coupling", within_hours, selection_mode
        )

        metrics_response = ChipMetricsResponse(
            chip_id=chip_id,
            username=username,
            qubit_count=qubit_count,
            within_hours=within_hours,
            qubit_metrics=qubit_metrics_data,
            coupling_metrics=coupling_metrics_data,
        )

        try:
            generator = MetricsPDFGenerator(
                metrics_response=metrics_response,
                within_hours=within_hours,
                selection_mode=selection_mode,
                topology_id=chip.topology_id,
            )
            pdf_buffer = generator.generate_pdf()
        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}")
            raise HTTPException(status_code=500, detail=f"PDF generation failed: {e!s}") from e

        timestamp = now().strftime("%Y%m%d_%H%M%S")
        filename = f"metrics_report_{chip_id}_{timestamp}.pdf"

        return pdf_buffer, filename, chip.topology_id

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
