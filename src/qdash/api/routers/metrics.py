"""Metrics API router for chip calibration metrics visualization."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from bunnet import SortDirection
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from qdash.api.lib.metrics_config import load_metrics_config
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.metrics import (
    ChipMetricsResponse,
    MetricHistoryItem,
    MetricValue,
    QubitMetricHistoryResponse,
)
from qdash.common.datetime_utils import now, to_datetime
from qdash.repository.chip import MongoChipRepository
from qdash.repository.task_result_history import MongoTaskResultHistoryRepository

router = APIRouter()
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


@router.get("/config", summary="Get metrics configuration", operation_id="getMetricsConfig")
async def get_metrics_config() -> dict[str, Any]:
    """Get metrics metadata configuration for visualization.

    Retrieves the metrics configuration loaded from YAML, including display
    metadata for all qubit and coupling metrics used in the dashboard.

    Returns
    -------
    dict[str, Any]
        Dictionary with metrics configuration including:
        - qubit_metrics: Metadata for single-qubit metrics (frequency, T1, T2, fidelities)
        - coupling_metrics: Metadata for two-qubit coupling metrics (ZX90, Bell state)
        - color_scale: Color scale configuration for heatmap visualization

    """
    config = load_metrics_config()
    return dict(config.model_dump())


def _extract_latest_metrics(
    chip_id: str,
    project_id: str,
    entity_type: Literal["qubit", "coupling"],
    valid_metric_keys: set[str],
    cutoff_time: Any | None,
) -> dict[str, dict[str, MetricValue]]:
    """Extract latest metrics from task result history using aggregation.

    Uses MongoDB aggregation pipeline for efficient retrieval of the most recent
    successful metric values for each entity. Only completed tasks are included
    to ensure grid displays successful results only.

    Args:
    ----
        chip_id: The chip identifier
        project_id: The project identifier for filtering (allows all project members to see metrics)
        entity_type: Type of entity - either "qubit" or "coupling"
        valid_metric_keys: Set of metric keys to extract from config
        cutoff_time: Optional datetime for filtering tasks

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue with latest values

    """
    if not valid_metric_keys:
        return {key: {} for key in valid_metric_keys}

    try:
        task_result_repo = MongoTaskResultHistoryRepository()
        agg_results = task_result_repo.aggregate_latest_metrics(
            chip_id=chip_id,
            project_id=project_id,
            entity_type=entity_type,
            metric_keys=valid_metric_keys,
            cutoff_time=cutoff_time,
        )
    except Exception as e:
        logger.error(f"Failed to aggregate latest metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}") from e

    # Convert aggregation results to MetricValue format
    metrics_data: dict[str, dict[str, MetricValue]] = {key: {} for key in valid_metric_keys}

    for metric_name, entity_values in agg_results.items():
        for entity_id, result in entity_values.items():
            metrics_data[metric_name][entity_id] = MetricValue(
                value=result["value"],
                task_id=result["task_id"],
                execution_id=result["execution_id"],
            )

    return metrics_data


def _extract_best_metrics(
    chip_id: str,
    project_id: str,
    entity_type: Literal["qubit", "coupling"],
    valid_metric_keys: set[str],
    metrics_config: dict[str, Any],
    cutoff_time: Any | None,
) -> dict[str, dict[str, MetricValue]]:
    """Extract best metrics from task result history using aggregation.

    Uses MongoDB aggregation pipeline to efficiently find the optimal metric values
    based on the evaluation mode (maximize/minimize) defined in the configuration.

    Args:
    ----
        chip_id: The chip identifier
        project_id: The project identifier for filtering (allows all project members to see metrics)
        entity_type: Type of entity - either "qubit" or "coupling"
        valid_metric_keys: Set of metric keys to extract from config
        metrics_config: Metrics configuration mapping metric_key -> MetricMetadata
        cutoff_time: Optional datetime for filtering tasks

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue with best values

    """
    metrics_data: dict[str, dict[str, MetricValue]] = {key: {} for key in valid_metric_keys}

    # Build metric_modes dict for metrics that support best mode (evaluation.mode != "none")
    metric_modes: dict[str, Literal["maximize", "minimize"]] = {}
    for key in valid_metric_keys:
        mode = metrics_config[key].evaluation.mode
        if mode in ("maximize", "minimize"):
            metric_modes[key] = mode

    if not metric_modes:
        return metrics_data

    try:
        task_result_repo = MongoTaskResultHistoryRepository()
        agg_results = task_result_repo.aggregate_best_metrics(
            chip_id=chip_id,
            project_id=project_id,
            entity_type=entity_type,
            metric_modes=metric_modes,
            cutoff_time=cutoff_time,
        )
    except Exception as e:
        logger.error(f"Failed to aggregate best metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}") from e

    # Convert aggregation results to MetricValue format
    for metric_name, entity_values in agg_results.items():
        for entity_id, result in entity_values.items():
            metrics_data[metric_name][entity_id] = MetricValue(
                value=result["value"],
                task_id=result["task_id"],
                execution_id=result["execution_id"],
            )

    return metrics_data


def _extract_average_metrics(
    chip_id: str,
    project_id: str,
    entity_type: Literal["qubit", "coupling"],
    valid_metric_keys: set[str],
    cutoff_time: Any | None,
) -> dict[str, dict[str, MetricValue]]:
    """Extract average metrics from task result history using aggregation.

    Uses MongoDB aggregation pipeline to compute the mean value for each
    (entity, metric) combination. Null values are excluded before averaging.

    Args:
    ----
        chip_id: The chip identifier
        project_id: The project identifier for filtering
        entity_type: Type of entity - either "qubit" or "coupling"
        valid_metric_keys: Set of metric keys to extract from config
        cutoff_time: Optional datetime for filtering tasks

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue with average values

    """
    if not valid_metric_keys:
        return {key: {} for key in valid_metric_keys}

    try:
        task_result_repo = MongoTaskResultHistoryRepository()
        agg_results = task_result_repo.aggregate_average_metrics(
            chip_id=chip_id,
            project_id=project_id,
            entity_type=entity_type,
            metric_keys=valid_metric_keys,
            cutoff_time=cutoff_time,
        )
    except Exception as e:
        logger.error(f"Failed to aggregate average metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}") from e

    # Convert aggregation results to MetricValue format
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


def extract_qubit_metrics(
    chip_id: str,
    project_id: str,
    within_hours: int | None = None,
    selection_mode: Literal["latest", "best", "average"] = "latest",
) -> dict[str, dict[str, MetricValue]]:
    """Extract qubit metrics from task result history.

    Args:
    ----
        chip_id: The chip identifier
        project_id: The project identifier for filtering (allows all project members to see metrics)
        within_hours: Optional time filter in hours (e.g., 24 for last 24 hours)
        selection_mode: "latest" for most recent, "best" for optimal, "average" for mean value

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue

    """
    # Get valid metric keys from config
    config = load_metrics_config()
    valid_metric_keys = set(config.qubit_metrics.keys())

    # Determine cutoff time if filtering
    cutoff_time = None
    if within_hours:
        cutoff_time = now() - timedelta(hours=within_hours)

    # Extract metrics based on selection mode
    if selection_mode == "latest":
        return _extract_latest_metrics(chip_id, project_id, "qubit", valid_metric_keys, cutoff_time)
    if selection_mode == "average":
        return _extract_average_metrics(
            chip_id, project_id, "qubit", valid_metric_keys, cutoff_time
        )
    return _extract_best_metrics(
        chip_id, project_id, "qubit", valid_metric_keys, config.qubit_metrics, cutoff_time
    )


def extract_coupling_metrics(
    chip_id: str,
    project_id: str,
    within_hours: int | None = None,
    selection_mode: Literal["latest", "best", "average"] = "latest",
) -> dict[str, dict[str, MetricValue]]:
    """Extract coupling metrics from task result history.

    Args:
    ----
        chip_id: The chip identifier
        project_id: The project identifier for filtering (allows all project members to see metrics)
        within_hours: Optional time filter in hours
        selection_mode: "latest" for most recent, "best" for optimal, "average" for mean value

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue

    """
    # Get valid metric keys from config
    config = load_metrics_config()
    valid_metric_keys = set(config.coupling_metrics.keys())

    # Determine cutoff time if filtering
    cutoff_time = None
    if within_hours:
        cutoff_time = now() - timedelta(hours=within_hours)

    # Extract metrics based on selection mode
    if selection_mode == "latest":
        return _extract_latest_metrics(
            chip_id, project_id, "coupling", valid_metric_keys, cutoff_time
        )
    if selection_mode == "average":
        return _extract_average_metrics(
            chip_id, project_id, "coupling", valid_metric_keys, cutoff_time
        )
    return _extract_best_metrics(
        chip_id, project_id, "coupling", valid_metric_keys, config.coupling_metrics, cutoff_time
    )


@router.get(
    "/chips/{chip_id}/metrics", response_model=ChipMetricsResponse, operation_id="getChipMetrics"
)
async def get_chip_metrics(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    within_hours: Annotated[
        int | None, Query(description="Filter to data within N hours (e.g., 24)")
    ] = None,
    selection_mode: Annotated[
        Literal["latest", "best", "average"],
        Query(
            description="Selection mode: 'latest' for most recent, 'best' for optimal, 'average' for mean values"
        ),
    ] = "latest",
) -> ChipMetricsResponse:
    """Get chip calibration metrics for visualization.

    This endpoint returns calibration metrics for a specific chip from the database, including:
    - Qubit frequency, anharmonicity, T1, T2 echo times
    - Gate fidelities (single-qubit and two-qubit)
    - Readout fidelities

    Args:
    ----
        chip_id: The chip identifier
        ctx: Project context with user and project information
        within_hours: Optional filter to only include data from last N hours (e.g., 24)
        selection_mode: "latest" to get most recent values, "best" to get optimal values

    Returns:
    -------
        ChipMetricsResponse with all metrics data

    """
    # Get chip existence and entity models from repository (scalable approach)
    chip_repo = MongoChipRepository()

    # Check if chip exists and get qubit count
    qubit_count = chip_repo.get_qubit_count(ctx.project_id, chip_id)
    if qubit_count == 0:
        # Check if chip exists at all
        chip = chip_repo.find_one_document({"project_id": ctx.project_id, "chip_id": chip_id})
        if not chip:
            raise HTTPException(
                status_code=404, detail=f"Chip {chip_id} not found in project {ctx.project_id}"
            )

    # Extract metrics from task result history (project-scoped for all members)
    qubit_metrics = extract_qubit_metrics(chip_id, ctx.project_id, within_hours, selection_mode)
    coupling_metrics = extract_coupling_metrics(
        chip_id, ctx.project_id, within_hours, selection_mode
    )

    return ChipMetricsResponse(
        chip_id=chip_id,
        username=ctx.user.username,
        qubit_count=qubit_count,
        within_hours=within_hours,
        qubit_metrics=qubit_metrics,
        coupling_metrics=coupling_metrics,
    )


@router.get(
    "/chips/{chip_id}/qubits/{qid}/history",
    response_model=QubitMetricHistoryResponse,
    operation_id="getQubitMetricHistory",
)
async def get_qubit_metric_history(
    chip_id: str,
    qid: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    metric: Annotated[str, Query(description="Metric name (e.g., t1, qubit_frequency)")],
    limit: Annotated[
        int | None, Query(description="Max number of history items (None for unlimited)", ge=1)
    ] = None,
    within_days: Annotated[int | None, Query(description="Filter to last N days", ge=1)] = 30,
) -> QubitMetricHistoryResponse:
    """Get historical metric data for a specific qubit with task_id for figure display.

    This endpoint queries TaskResultHistoryDocument to retrieve calibration
    history for a specific metric, including multiple executions on the same day.
    Each history item includes task_id for displaying calibration figures.

    Args:
    ----
        chip_id: The chip identifier
        qid: The qubit identifier (e.g., "0", "Q00")
        ctx: Project context with user and project information
        metric: Metric name to retrieve history for
        limit: Maximum number of history items (None for unlimited within time range)
        within_days: Optional filter to only include data from last N days

    Returns:
    -------
        QubitMetricHistoryResponse with historical metric data and task_ids

    """
    # Normalize qid format (remove "Q" prefix if present)
    normalized_qid = normalize_qid(qid)
    qid_variants = list({normalized_qid, qid, f"Q{normalized_qid.zfill(2)}"})

    # Calculate cutoff time
    cutoff_time = None
    if within_days:
        cutoff_time = now() - timedelta(days=within_days)

    # Query task result history directly for matching metrics (scoped by project)
    query: dict[str, Any] = {
        "project_id": ctx.project_id,
        "chip_id": chip_id,
        "task_type": "qubit",
        "qid": {"$in": qid_variants},
        f"output_parameters.{metric}": {"$exists": True},
    }

    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time}

    task_result_repo = MongoTaskResultHistoryRepository()
    task_results = task_result_repo.find(
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
            "No task history found for project=%s, chip=%s, qid=%s (normalized=%s), metric=%s",
            ctx.project_id,
            chip_id,
            qid,
            normalized_qid,
            metric,
        )

    return QubitMetricHistoryResponse(
        chip_id=chip_id,
        qid=qid,
        metric_name=metric,
        username=ctx.user.username,
        history=history_items,
    )


@router.get(
    "/chips/{chip_id}/couplings/{coupling_id}/history",
    response_model=QubitMetricHistoryResponse,
    operation_id="getCouplingMetricHistory",
)
async def get_coupling_metric_history(
    chip_id: str,
    coupling_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    metric: Annotated[
        str, Query(description="Metric name (e.g., zx90_gate_fidelity, bell_state_fidelity)")
    ],
    limit: Annotated[
        int | None, Query(description="Max number of history items (None for unlimited)", ge=1)
    ] = None,
    within_days: Annotated[int | None, Query(description="Filter to last N days", ge=1)] = 30,
) -> QubitMetricHistoryResponse:
    """Get historical metric data for a specific coupling with task_id for figure display.

    This endpoint queries TaskResultHistoryDocument to retrieve calibration
    history for a specific coupling metric, including multiple executions on the same day.
    Each history item includes task_id for displaying calibration figures.

    Args:
    ----
        chip_id: The chip identifier
        coupling_id: The coupling identifier (e.g., "0-1", "2-3")
        ctx: Project context with user and project information
        metric: Metric name to retrieve history for
        limit: Maximum number of history items (None for unlimited within time range)
        within_days: Optional filter to only include data from last N days

    Returns:
    -------
        QubitMetricHistoryResponse with historical metric data and task_ids
        (Note: qid field contains coupling_id for coupling metrics)

    """
    # Calculate cutoff time
    cutoff_time = None
    if within_days:
        cutoff_time = now() - timedelta(days=within_days)

    query: dict[str, Any] = {
        "project_id": ctx.project_id,
        "chip_id": chip_id,
        "task_type": "coupling",
        "qid": coupling_id,
        f"output_parameters.{metric}": {"$exists": True},
    }

    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time}

    task_result_repo = MongoTaskResultHistoryRepository()
    task_results = task_result_repo.find(
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
            "No task history found for project=%s, chip=%s, coupling_id=%s, metric=%s",
            ctx.project_id,
            chip_id,
            coupling_id,
            metric,
        )

    return QubitMetricHistoryResponse(
        chip_id=chip_id,
        qid=coupling_id,  # Reuse qid field for coupling_id
        metric_name=metric,
        username=ctx.user.username,
        history=history_items,
    )


@router.post(
    "/chips/{chip_id}/metrics/pdf",
    summary="Download metrics as PDF report",
    operation_id="downloadMetricsPdf",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF report file",
        }
    },
)
async def download_metrics_pdf(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    within_hours: Annotated[int | None, Query(description="Filter to data within N hours")] = None,
    selection_mode: Annotated[
        Literal["latest", "best", "average"],
        Query(description="Selection mode: 'latest', 'best', or 'average'"),
    ] = "latest",
) -> StreamingResponse:
    """Download chip metrics as a PDF report.

    Generates a comprehensive PDF report containing:
    - Cover page with chip information and report metadata
    - Heatmap visualizations for each metric
    - Statistics for each metric (coverage, average, min, max, std dev)

    The report includes all qubit metrics (8 types) and coupling metrics (3 types)
    that have data available.

    Args:
        chip_id: Chip identifier
        within_hours: Optional time filter in hours
        selection_mode: "latest" for most recent values, "best" for optimal values
    """
    from qdash.api.lib.metrics_pdf import MetricsPDFGenerator

    # Get chip document (needed for topology_id)
    chip_repo = MongoChipRepository()
    chip = chip_repo.find_one_document(
        {
            "project_id": ctx.project_id,
            "chip_id": chip_id,
        }
    )

    if not chip:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")

    # Get qubit count for PDF report
    qubit_count = chip_repo.get_qubit_count(ctx.project_id, chip_id)

    # Calculate cutoff time if time filter specified
    cutoff_time = None
    if within_hours:
        cutoff_time = now() - timedelta(hours=within_hours)

    # Load metrics configuration
    config = load_metrics_config()

    # Extract metrics based on selection mode (project-scoped for all members)
    if selection_mode == "latest":
        qubit_metrics_data = _extract_latest_metrics(
            chip_id=chip_id,
            project_id=ctx.project_id,
            entity_type="qubit",
            valid_metric_keys=set(config.qubit_metrics.keys()),
            cutoff_time=cutoff_time,
        )
        coupling_metrics_data = _extract_latest_metrics(
            chip_id=chip_id,
            project_id=ctx.project_id,
            entity_type="coupling",
            valid_metric_keys=set(config.coupling_metrics.keys()),
            cutoff_time=cutoff_time,
        )
    elif selection_mode == "average":
        qubit_metrics_data = _extract_average_metrics(
            chip_id=chip_id,
            project_id=ctx.project_id,
            entity_type="qubit",
            valid_metric_keys=set(config.qubit_metrics.keys()),
            cutoff_time=cutoff_time,
        )
        coupling_metrics_data = _extract_average_metrics(
            chip_id=chip_id,
            project_id=ctx.project_id,
            entity_type="coupling",
            valid_metric_keys=set(config.coupling_metrics.keys()),
            cutoff_time=cutoff_time,
        )
    else:
        qubit_metrics_data = _extract_best_metrics(
            chip_id=chip_id,
            project_id=ctx.project_id,
            entity_type="qubit",
            valid_metric_keys=set(config.qubit_metrics.keys()),
            metrics_config=config.qubit_metrics,
            cutoff_time=cutoff_time,
        )
        coupling_metrics_data = _extract_best_metrics(
            chip_id=chip_id,
            project_id=ctx.project_id,
            entity_type="coupling",
            valid_metric_keys=set(config.coupling_metrics.keys()),
            metrics_config=config.coupling_metrics,
            cutoff_time=cutoff_time,
        )

    # Build response model (reuse logic from getChipMetrics)
    metrics_response = ChipMetricsResponse(
        chip_id=chip_id,
        username=ctx.user.username,
        qubit_count=qubit_count,
        within_hours=within_hours,
        qubit_metrics=qubit_metrics_data,
        coupling_metrics=coupling_metrics_data,
    )

    # Generate PDF
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

    # Generate filename
    timestamp = now().strftime("%Y%m%d_%H%M%S")
    filename = f"metrics_report_{chip_id}_{timestamp}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
