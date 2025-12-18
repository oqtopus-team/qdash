"""Metrics API router for chip calibration metrics visualization."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

import pendulum
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from qdash.api.lib.metrics_config import load_metrics_config
from qdash.api.lib.project import ProjectContext, get_project_context
from qdash.api.schemas.metrics import (
    ChipMetricsResponse,
    CouplingMetrics,
    MetricHistoryItem,
    MetricValue,
    QubitMetricHistoryResponse,
    QubitMetrics,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

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
) -> tuple[float | int | None, str | None, str | None]:
    """Extract value, calibrated_at, and task_id from metric output data."""

    if metric_data is None:
        return None, None, None

    if isinstance(metric_data, dict):
        return (
            metric_data.get("value"),
            metric_data.get("calibrated_at"),
            metric_data.get("task_id"),
        )

    if hasattr(metric_data, "model_dump"):
        data = metric_data.model_dump()
        return data.get("value"), data.get("calibrated_at"), data.get("task_id")

    if hasattr(metric_data, "value"):
        return (
            getattr(metric_data, "value", None),
            getattr(metric_data, "calibrated_at", None),
            getattr(metric_data, "task_id", None),
        )

    return metric_data, None, None


def _get_task_timestamp(task_doc: Any) -> str:
    """Get the best available timestamp for a task history document."""

    timestamp = getattr(task_doc, "start_at", "") or getattr(task_doc, "end_at", "")
    if timestamp:
        return timestamp

    system_info = getattr(task_doc, "system_info", None)
    if isinstance(system_info, dict):
        return str(system_info.get("created_at", ""))

    return getattr(system_info, "created_at", "") if system_info is not None else ""


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
    entity_models: dict[str, Any],
    valid_metric_keys: set[str],
    cutoff_time: Any | None,
    within_hours: int | None,
) -> dict[str, dict[str, MetricValue]]:
    """Extract latest metrics from chip document entities (qubits or couplings).

    This function extracts the most recent calibration data directly from the
    ChipDocument. If a time filter is specified, only metrics calibrated within
    that window are included.

    Args:
    ----
        entity_models: Dictionary of qubit/coupling models from ChipDocument
        valid_metric_keys: Set of metric keys to extract from config
        cutoff_time: Optional pendulum datetime for filtering calibration times
        within_hours: Number of hours for time window (used for logging)

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue with latest values

    Notes:
    -----
        - Reads from ChipDocument.qubits or ChipDocument.couplings
        - Filters by calibrated_at timestamp if within_hours is specified
        - Returns empty dict for metrics with no valid data

    """
    metrics_data: dict[str, dict[str, MetricValue]] = {key: {} for key in valid_metric_keys}

    for entity_id, entity_model in entity_models.items():
        if entity_model.data and isinstance(entity_model.data, dict):
            for param_name, param_data in entity_model.data.items():
                if isinstance(param_data, dict) and "value" in param_data:
                    # Check time filter
                    include_param = True
                    if within_hours and cutoff_time is not None and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(
                                param_data["calibrated_at"], tz="Asia/Tokyo"
                            )
                            include_param = calibrated_at >= cutoff_time
                        except Exception:
                            include_param = False

                    if include_param and param_name in valid_metric_keys:
                        value = param_data.get("value")
                        task_id = param_data.get("task_id", "")
                        execution_id = param_data.get("execution_id", "")

                        # Store the value with metadata
                        metrics_data[param_name][entity_id] = MetricValue(
                            value=value,
                            task_id=task_id if task_id else None,
                            execution_id=execution_id if execution_id else None,
                        )

    return metrics_data


def _extract_best_metrics(
    chip: ChipDocument,
    entity_type: Literal["qubit", "coupling"],
    valid_metric_keys: set[str],
    metrics_config: dict[str, Any],
    cutoff_time: Any | None,
) -> dict[str, dict[str, MetricValue]]:
    """Extract best metrics from task result history.

    This function queries TaskResultHistoryDocument to find the optimal metric values
    based on the evaluation mode (maximize/minimize) defined in the configuration.
    It processes all task results within the specified time window and selects the
    best value for each metric.

    Args:
    ----
        chip: Chip document containing chip_id and username
        entity_type: Type of entity - either "qubit" or "coupling"
        valid_metric_keys: Set of metric keys to extract from config
        metrics_config: Metrics configuration mapping metric_key -> MetricMetadata
        cutoff_time: Optional pendulum datetime for filtering tasks

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue with best values

    Notes:
    -----
        - Only processes metrics with evaluation.mode != "none"
        - Queries TaskResultHistoryDocument for output_parameters
        - Uses max() for "maximize" mode and min() for "minimize" mode

    """
    metrics_data: dict[str, dict[str, MetricValue]] = {key: {} for key in valid_metric_keys}

    # Filter to only metrics that support best mode (evaluation.mode != "none")
    best_mode_metrics = [
        key for key in valid_metric_keys if metrics_config[key].evaluation.mode != "none"
    ]

    if not best_mode_metrics:
        return metrics_data

    # Build query for task result history with metric existence filter
    # This significantly reduces the number of documents fetched from MongoDB
    query: dict[str, Any] = {
        "chip_id": chip.chip_id,
        "username": chip.username,
        "task_type": entity_type,
        "$or": [{f"output_parameters.{metric}": {"$exists": True}} for metric in best_mode_metrics],
    }
    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time.to_iso8601_string()}

    # Query task results that have at least one of the target metrics
    try:
        task_results = TaskResultHistoryDocument.find(query).sort([("start_at", -1)]).to_list()
    except Exception as e:
        logger.error(f"Failed to query task result history: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}") from e

    if not task_results:
        logger.warning(
            f"No task result history found for chip={chip.chip_id}, username={chip.username}"
        )
        return metrics_data

    # Collect all values for each metric/entity_id combination
    # Structure: metric_name -> entity_id -> list of (value, task_id, execution_id, calibrated_at)
    metric_values: dict[str, dict[str, list[tuple[float, str, str, str]]]] = {
        key: {} for key in valid_metric_keys
    }

    for task_doc in task_results:
        entity_id = task_doc.qid
        if not entity_id:
            continue

        output_params = task_doc.output_parameters
        if not output_params:
            continue

        for metric_name in valid_metric_keys:
            if metric_name not in output_params:
                continue

            metric_data = output_params[metric_name]

            # Extract value from output_parameters
            if isinstance(metric_data, dict):
                value = metric_data.get("value")
                task_id = metric_data.get("task_id", task_doc.task_id)
                execution_id = metric_data.get("execution_id", task_doc.execution_id)
                calibrated_at = metric_data.get("calibrated_at", task_doc.start_at)
            else:
                value = metric_data
                task_id = task_doc.task_id
                execution_id = task_doc.execution_id
                calibrated_at = task_doc.start_at

            if value is not None and isinstance(value, (int, float)):
                if entity_id not in metric_values[metric_name]:
                    metric_values[metric_name][entity_id] = []
                metric_values[metric_name][entity_id].append(
                    (float(value), task_id or "", execution_id, calibrated_at)
                )

    # Select best value for each metric/entity_id based on evaluation mode
    for metric_name in valid_metric_keys:
        metric_config = metrics_config[metric_name]
        eval_mode = metric_config.evaluation.mode

        if eval_mode == "none":
            # For 'none' mode, skip in best mode
            continue

        for entity_id, values in metric_values[metric_name].items():
            if not values:
                continue

            # Select best value according to evaluation mode
            if eval_mode == "maximize":
                best_entry = max(values, key=lambda x: x[0])
            elif eval_mode == "minimize":
                best_entry = min(values, key=lambda x: x[0])
            else:
                continue

            best_value, best_task_id, best_execution_id, _ = best_entry
            metrics_data[metric_name][entity_id] = MetricValue(
                value=best_value,
                task_id=best_task_id if best_task_id else None,
                execution_id=best_execution_id,
            )

    return metrics_data


def extract_qubit_metrics(
    chip: ChipDocument,
    within_hours: int | None = None,
    selection_mode: Literal["latest", "best"] = "latest",
) -> QubitMetrics:
    """Extract qubit metrics from ChipDocument.

    Args:
    ----
        chip: The chip document
        within_hours: Optional time filter in hours (e.g., 24 for last 24 hours)
        selection_mode: "latest" to get most recent value, "best" to get optimal value within time range

    Returns:
    -------
        QubitMetrics with all qubit-level metrics

    """
    # Get valid metric keys from config
    config = load_metrics_config()
    valid_metric_keys = set(config.qubit_metrics.keys())

    # Determine cutoff time if filtering
    cutoff_time = None
    if within_hours:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=within_hours)

    # Extract metrics based on selection mode
    if selection_mode == "latest":
        metrics_data = _extract_latest_metrics(
            chip.qubits, valid_metric_keys, cutoff_time, within_hours
        )
    else:
        metrics_data = _extract_best_metrics(
            chip, "qubit", valid_metric_keys, config.qubit_metrics, cutoff_time
        )

    # Build QubitMetrics response
    return QubitMetrics(
        qubit_frequency=metrics_data.get("qubit_frequency") or None,
        anharmonicity=metrics_data.get("anharmonicity") or None,
        t1=metrics_data.get("t1") or None,
        t2_echo=metrics_data.get("t2_echo") or None,
        t2_star=metrics_data.get("t2_star") or None,
        average_readout_fidelity=metrics_data.get("average_readout_fidelity") or None,
        x90_gate_fidelity=metrics_data.get("x90_gate_fidelity") or None,
        x180_gate_fidelity=metrics_data.get("x180_gate_fidelity") or None,
    )


def extract_coupling_metrics(
    chip: ChipDocument,
    within_hours: int | None = None,
    selection_mode: Literal["latest", "best"] = "latest",
) -> CouplingMetrics:
    """Extract coupling metrics from ChipDocument.

    Args:
    ----
        chip: The chip document
        within_hours: Optional time filter in hours
        selection_mode: "latest" to get most recent value, "best" to get optimal value within time range

    Returns:
    -------
        CouplingMetrics with all coupling-level metrics

    """
    # Get valid metric keys from config
    config = load_metrics_config()
    valid_metric_keys = set(config.coupling_metrics.keys())

    # Determine cutoff time if filtering
    cutoff_time = None
    if within_hours:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=within_hours)

    # Extract metrics based on selection mode
    if selection_mode == "latest":
        metrics_data = _extract_latest_metrics(
            chip.couplings, valid_metric_keys, cutoff_time, within_hours
        )
    else:
        metrics_data = _extract_best_metrics(
            chip, "coupling", valid_metric_keys, config.coupling_metrics, cutoff_time
        )

    return CouplingMetrics(
        zx90_gate_fidelity=metrics_data.get("zx90_gate_fidelity") or None,
        bell_state_fidelity=metrics_data.get("bell_state_fidelity") or None,
        static_zz_interaction=metrics_data.get("static_zz_interaction") or None,
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
        Literal["latest", "best"],
        Query(description="Selection mode: 'latest' for most recent, 'best' for optimal values"),
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
    # Get chip document from database (scoped by project)
    chip = ChipDocument.find_one({"project_id": ctx.project_id, "chip_id": chip_id}).run()

    if not chip:
        raise HTTPException(
            status_code=404, detail=f"Chip {chip_id} not found in project {ctx.project_id}"
        )

    # Extract metrics
    qubit_metrics = extract_qubit_metrics(chip, within_hours, selection_mode)
    coupling_metrics = extract_coupling_metrics(chip, within_hours, selection_mode)

    return ChipMetricsResponse(
        chip_id=chip_id,
        username=ctx.user.username,
        qubit_count=len(chip.qubits),
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
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(days=within_days)

    # Query task result history directly for matching metrics (scoped by project)
    query: dict[str, Any] = {
        "project_id": ctx.project_id,
        "chip_id": chip_id,
        "task_type": "qubit",
        "qid": {"$in": qid_variants},
        f"output_parameters.{metric}": {"$exists": True},
    }

    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time.to_iso8601_string()}

    results_query = TaskResultHistoryDocument.find(query).sort([("start_at", -1)])
    if limit is not None:
        results_query = results_query.limit(limit)

    task_results = results_query.run()

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
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(days=within_days)

    query: dict[str, Any] = {
        "project_id": ctx.project_id,
        "chip_id": chip_id,
        "task_type": "coupling",
        "qid": coupling_id,
        f"output_parameters.{metric}": {"$exists": True},
    }

    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time.to_iso8601_string()}

    results_query = TaskResultHistoryDocument.find(query).sort([("start_at", -1)])
    if limit is not None:
        results_query = results_query.limit(limit)

    task_results = results_query.run()

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
        Literal["latest", "best"], Query(description="Selection mode: 'latest' or 'best'")
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

    # Get chip document
    chip = ChipDocument.find_one(
        ChipDocument.project_id == ctx.project_id,
        ChipDocument.chip_id == chip_id,
        ChipDocument.username == ctx.user.username,
    ).run()

    if not chip:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found")

    # Calculate cutoff time if time filter specified
    cutoff_time = None
    if within_hours:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=within_hours)

    # Load metrics configuration
    config = load_metrics_config()

    # Extract metrics based on selection mode
    if selection_mode == "latest":
        qubit_metrics_data = _extract_latest_metrics(
            entity_models=chip.qubits,
            valid_metric_keys=set(config.qubit_metrics.keys()),
            cutoff_time=cutoff_time,
            within_hours=within_hours,
        )
        coupling_metrics_data = _extract_latest_metrics(
            entity_models=chip.couplings,
            valid_metric_keys=set(config.coupling_metrics.keys()),
            cutoff_time=cutoff_time,
            within_hours=within_hours,
        )
    else:
        qubit_metrics_data = _extract_best_metrics(
            chip=chip,
            entity_type="qubit",
            valid_metric_keys=set(config.qubit_metrics.keys()),
            metrics_config=config.qubit_metrics,
            cutoff_time=cutoff_time,
        )
        coupling_metrics_data = _extract_best_metrics(
            chip=chip,
            entity_type="coupling",
            valid_metric_keys=set(config.coupling_metrics.keys()),
            metrics_config=config.coupling_metrics,
            cutoff_time=cutoff_time,
        )

    # Build response model (reuse logic from getChipMetrics)
    # Map config keys to schema keys for qubit metrics
    qubit_metrics_mapped = {}
    for config_key, data in qubit_metrics_data.items():
        schema_key = "qubit_frequency" if config_key == "bare_frequency" else config_key
        qubit_metrics_mapped[schema_key] = data

    metrics_response = ChipMetricsResponse(
        chip_id=chip_id,
        username=ctx.user.username,
        qubit_count=len(chip.qubits),
        within_hours=within_hours,
        qubit_metrics=QubitMetrics(**qubit_metrics_mapped),
        coupling_metrics=CouplingMetrics(**coupling_metrics_data),
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
    timestamp = pendulum.now("Asia/Tokyo").format("YYYYMMDD_HHmmss")
    filename = f"metrics_report_{chip_id}_{timestamp}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
