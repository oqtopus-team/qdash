"""Metrics API router for chip calibration metrics visualization."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

import pendulum
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from qdash.api.lib.auth import get_optional_current_user
from qdash.api.lib.metrics_config import load_metrics_config
from qdash.api.schemas.auth import User
from qdash.dbmodel.chip import ChipDocument

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


@router.get("/config")
async def get_metrics_config() -> dict[str, Any]:
    """Get metrics metadata configuration.

    This endpoint returns the metrics configuration loaded from YAML,
    including display metadata for all qubit and coupling metrics.

    Returns
    -------
        Dictionary with metrics configuration including:
        - qubit_metrics: Metadata for single-qubit metrics
        - coupling_metrics: Metadata for two-qubit coupling metrics
        - color_scale: Color scale configuration for visualization

    """
    config = load_metrics_config()
    return config.model_dump()


class MetricValue(BaseModel):
    """Single metric value with metadata."""

    value: float | None = None
    task_id: str | None = None
    execution_id: str | None = None


class QubitMetrics(BaseModel):
    """Single qubit metrics data."""

    qubit_frequency: dict[str, MetricValue] | None = None
    anharmonicity: dict[str, MetricValue] | None = None
    t1: dict[str, MetricValue] | None = None
    t2_echo: dict[str, MetricValue] | None = None
    t2_star: dict[str, MetricValue] | None = None
    average_readout_fidelity: dict[str, MetricValue] | None = None
    x90_gate_fidelity: dict[str, MetricValue] | None = None
    x180_gate_fidelity: dict[str, MetricValue] | None = None


class CouplingMetrics(BaseModel):
    """Two-qubit coupling metrics data."""

    zx90_gate_fidelity: dict[str, MetricValue] | None = None
    bell_state_fidelity: dict[str, MetricValue] | None = None
    static_zz_interaction: dict[str, MetricValue] | None = None


class ChipMetricsResponse(BaseModel):
    """Complete chip metrics response."""

    chip_id: str
    username: str
    qubit_count: int
    within_hours: int | None = None
    qubit_metrics: QubitMetrics
    coupling_metrics: CouplingMetrics


class MetricHistoryItem(BaseModel):
    """Single historical metric data point."""

    value: float | None
    execution_id: str
    task_id: str | None = None
    timestamp: str
    calibrated_at: str | None = None


class QubitMetricHistoryResponse(BaseModel):
    """Historical metric data for a single qubit."""

    chip_id: str
    qid: str
    metric_name: str
    username: str
    history: list[MetricHistoryItem]


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
                    if within_hours and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
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
    """Extract best metrics from execution history.

    This function queries the execution history to find the optimal metric values
    based on the evaluation mode (maximize/minimize) defined in the configuration.
    It processes all executions within the specified time window and selects the
    best value for each metric.

    Args:
    ----
        chip: Chip document containing chip_id and username
        entity_type: Type of entity - either "qubit" or "coupling"
        valid_metric_keys: Set of metric keys to extract from config
        metrics_config: Metrics configuration mapping metric_key -> MetricMetadata
        cutoff_time: Optional pendulum datetime for filtering executions

    Returns:
    -------
        Dictionary mapping metric_name -> entity_id -> MetricValue with best values

    Raises:
    ------
        HTTPException: If query returns too many executions (>1000)

    Notes:
    -----
        - Only processes metrics with evaluation.mode != "none"
        - Limits query to 1000 executions to prevent memory issues
        - Uses max() for "maximize" mode and min() for "minimize" mode

    """
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument

    metrics_data: dict[str, dict[str, MetricValue]] = {key: {} for key in valid_metric_keys}

    # Query execution history with limit to prevent memory issues
    query: dict[str, Any] = {
        "chip_id": chip.chip_id,
        "username": chip.username,
    }
    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time.to_iso8601_string()}

    # Limit to 1000 most recent executions, sorted by start_at descending
    try:
        executions = ExecutionHistoryDocument.find(query).sort([("start_at", -1)]).limit(1000).to_list()
    except Exception as e:
        logger.error(f"Failed to query execution history: {e}")
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}") from e

    if not executions:
        logger.warning(f"No execution history found for chip={chip.chip_id}, username={chip.username}")
        return metrics_data

    # Collect all values for each metric/entity_id combination
    metric_values: dict[str, dict[str, list[tuple[float, str, str, str]]]] = {key: {} for key in valid_metric_keys}

    for exec_doc in executions:
        calib_data = exec_doc.calib_data
        if entity_type in calib_data:
            for entity_id, entity_data in calib_data[entity_type].items():
                for metric_name, metric_data in entity_data.items():
                    if metric_name not in valid_metric_keys:
                        continue

                    # Extract value
                    if isinstance(metric_data, dict):
                        value = metric_data.get("value")
                        task_id = metric_data.get("task_id")
                        execution_id = exec_doc.execution_id
                        calibrated_at = metric_data.get("calibrated_at", exec_doc.start_at)
                    else:
                        value = metric_data
                        task_id = None
                        execution_id = exec_doc.execution_id
                        calibrated_at = exec_doc.start_at

                    if value is not None:
                        if entity_id not in metric_values[metric_name]:
                            metric_values[metric_name][entity_id] = []
                        metric_values[metric_name][entity_id].append(
                            (value, task_id or "", execution_id, calibrated_at)
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
        metrics_data = _extract_latest_metrics(chip.qubits, valid_metric_keys, cutoff_time, within_hours)
    else:
        metrics_data = _extract_best_metrics(chip, "qubit", valid_metric_keys, config.qubit_metrics, cutoff_time)

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
        metrics_data = _extract_latest_metrics(chip.couplings, valid_metric_keys, cutoff_time, within_hours)
    else:
        metrics_data = _extract_best_metrics(chip, "coupling", valid_metric_keys, config.coupling_metrics, cutoff_time)

    return CouplingMetrics(
        zx90_gate_fidelity=metrics_data.get("zx90_gate_fidelity") or None,
        bell_state_fidelity=metrics_data.get("bell_state_fidelity") or None,
        static_zz_interaction=metrics_data.get("static_zz_interaction") or None,
    )


@router.get("/chip/{chip_id}/metrics", response_model=ChipMetricsResponse)
async def get_chip_metrics(
    chip_id: str,
    within_hours: Annotated[int | None, Query(description="Filter to data within N hours (e.g., 24)")] = None,
    selection_mode: Annotated[
        Literal["latest", "best"],
        Query(description="Selection mode: 'latest' for most recent, 'best' for optimal values"),
    ] = "latest",
    current_user: User | None = Depends(get_optional_current_user),
) -> ChipMetricsResponse:
    """Get chip calibration metrics for visualization.

    This endpoint returns calibration metrics for a specific chip from the database, including:
    - Qubit frequency, anharmonicity, T1, T2 echo times
    - Gate fidelities (single-qubit and two-qubit)
    - Readout fidelities

    Args:
    ----
        chip_id: The chip identifier
        within_hours: Optional filter to only include data from last N hours (e.g., 24)
        selection_mode: "latest" to get most recent values, "best" to get optimal values
        current_user: Current authenticated user

    Returns:
    -------
        ChipMetricsResponse with all metrics data

    """
    # Get username from current user
    username = current_user.username if current_user else "admin"

    # Get chip document from database
    chip = ChipDocument.find_one({"chip_id": chip_id, "username": username}).run()

    if not chip:
        raise HTTPException(status_code=404, detail=f"Chip {chip_id} not found for user {username}")

    # Extract metrics
    qubit_metrics = extract_qubit_metrics(chip, within_hours, selection_mode)
    coupling_metrics = extract_coupling_metrics(chip, within_hours, selection_mode)

    return ChipMetricsResponse(
        chip_id=chip_id,
        username=username,
        qubit_count=len(chip.qubits),
        within_hours=within_hours,
        qubit_metrics=qubit_metrics,
        coupling_metrics=coupling_metrics,
    )


@router.get("/chips")
async def list_chips(
    username: Annotated[str, Query(description="Username")] = "admin",
    _current_user: User | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Get list of available chips for a user.

    Args:
    ----
        username: Username to filter by
        _current_user: Current authenticated user

    Returns:
    -------
        Dictionary with list of chips

    """
    chips = ChipDocument.find({"username": username}).to_list()

    return {
        "chips": [
            {
                "chip_id": chip.chip_id,
                "username": chip.username,
                "size": chip.size,
                "installed_at": chip.installed_at,
                "qubit_count": len(chip.qubits),
                "coupling_count": len(chip.couplings),
            }
            for chip in chips
        ]
    }


@router.get("/chip/current")
async def get_current_chip(
    username: Annotated[str, Query(description="Username")] = "admin",
    _current_user: User | None = Depends(get_optional_current_user),
) -> dict[str, str]:
    """Get current chip for a user.

    Args:
    ----
        username: Username to filter by
        _current_user: Current authenticated user

    Returns:
    -------
        Dictionary with current chip_id

    """
    try:
        chip = ChipDocument.get_current_chip(username)
        return {"chip_id": chip.chip_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/chip/{chip_id}/qubit/{qid}/metric-history", response_model=QubitMetricHistoryResponse)
async def get_qubit_metric_history(
    chip_id: str,
    qid: str,
    metric: Annotated[str, Query(description="Metric name (e.g., t1, qubit_frequency)")],
    limit: Annotated[int, Query(description="Max number of history items", ge=1, le=100)] = 20,
    within_days: Annotated[int | None, Query(description="Filter to last N days", ge=1)] = 30,
    current_user: User | None = Depends(get_optional_current_user),
) -> QubitMetricHistoryResponse:
    """Get historical metric data for a specific qubit with task_id for figure display.

    This endpoint queries ExecutionHistoryDocument to retrieve the calibration
    history for a specific metric, including multiple executions on the same day.
    Each history item includes task_id for displaying calibration figures.

    Args:
    ----
        chip_id: The chip identifier
        qid: The qubit identifier (e.g., "0", "Q00")
        metric: Metric name to retrieve history for
        limit: Maximum number of history items to return (1-100)
        within_days: Optional filter to only include data from last N days
        current_user: Current authenticated user

    Returns:
    -------
        QubitMetricHistoryResponse with historical metric data and task_ids

    """
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument

    username = current_user.username if current_user else "admin"

    # Normalize qid format (remove "Q" prefix if present)
    normalized_qid = normalize_qid(qid)

    # Calculate cutoff time
    cutoff_time = None
    if within_days:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(days=within_days)

    # Query execution history
    # Note: No status filter - we want to include all executions (running, completed, failed)
    # because individual tasks may have succeeded even if the execution as a whole failed
    query: dict[str, Any] = {
        "chip_id": chip_id,
        "username": username,
    }

    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time.to_iso8601_string()}

    executions = (
        ExecutionHistoryDocument.find(query)
        .sort([("start_at", -1)])
        .limit(limit * 3)  # Get more to filter by metric availability
        .to_list()
    )

    # Extract metric values from calib_data
    history_items: list[MetricHistoryItem] = []

    for exec_doc in executions:
        calib_data = exec_doc.calib_data

        # Try both normalized and original qid formats
        qid_variants = [normalized_qid, qid, f"Q{normalized_qid.zfill(2)}"]

        for qid_variant in qid_variants:
            if "qubit" in calib_data and qid_variant in calib_data["qubit"]:
                qubit_data = calib_data["qubit"][qid_variant]

                if metric in qubit_data:
                    metric_data = qubit_data[metric]

                    # Handle both dict and direct value formats
                    if isinstance(metric_data, dict):
                        value = metric_data.get("value")
                        task_id = metric_data.get("task_id")
                        calibrated_at = metric_data.get("calibrated_at")
                    else:
                        value = metric_data
                        task_id = None
                        calibrated_at = None

                    # Only include if value exists
                    if value is not None:
                        history_items.append(
                            MetricHistoryItem(
                                value=value,
                                execution_id=exec_doc.execution_id,
                                task_id=task_id,
                                timestamp=exec_doc.start_at,
                                calibrated_at=calibrated_at,
                            )
                        )

                        # Stop once we have enough items
                        if len(history_items) >= limit:
                            break

                    # Break qid_variant loop if we found the metric
                    break

        # Break execution loop if we have enough items
        if len(history_items) >= limit:
            break

    if not history_items:
        logger.warning(f"No history found for chip={chip_id}, qid={qid} (normalized={normalized_qid}), metric={metric}")

    return QubitMetricHistoryResponse(
        chip_id=chip_id,
        qid=qid,
        metric_name=metric,
        username=username,
        history=history_items,
    )


@router.get("/chip/{chip_id}/coupling/{coupling_id}/metric-history", response_model=QubitMetricHistoryResponse)
async def get_coupling_metric_history(
    chip_id: str,
    coupling_id: str,
    metric: Annotated[str, Query(description="Metric name (e.g., zx90_gate_fidelity, bell_state_fidelity)")],
    limit: Annotated[int, Query(description="Max number of history items", ge=1, le=100)] = 20,
    within_days: Annotated[int | None, Query(description="Filter to last N days", ge=1)] = 30,
    current_user: User | None = Depends(get_optional_current_user),
) -> QubitMetricHistoryResponse:
    """Get historical metric data for a specific coupling with task_id for figure display.

    This endpoint queries ExecutionHistoryDocument to retrieve the calibration
    history for a specific coupling metric, including multiple executions on the same day.
    Each history item includes task_id for displaying calibration figures.

    Args:
    ----
        chip_id: The chip identifier
        coupling_id: The coupling identifier (e.g., "0-1", "2-3")
        metric: Metric name to retrieve history for
        limit: Maximum number of history items to return (1-100)
        within_days: Optional filter to only include data from last N days
        current_user: Current authenticated user

    Returns:
    -------
        QubitMetricHistoryResponse with historical metric data and task_ids
        (Note: qid field contains coupling_id for coupling metrics)

    """
    from qdash.dbmodel.execution_history import ExecutionHistoryDocument

    username = current_user.username if current_user else "admin"

    # Calculate cutoff time
    cutoff_time = None
    if within_days:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(days=within_days)

    # Query execution history
    # Note: No status filter - we want to include all executions (running, completed, failed)
    # because individual tasks may have succeeded even if the execution as a whole failed
    query: dict[str, Any] = {
        "chip_id": chip_id,
        "username": username,
    }

    if cutoff_time:
        query["start_at"] = {"$gte": cutoff_time.to_iso8601_string()}

    executions = (
        ExecutionHistoryDocument.find(query)
        .sort([("start_at", -1)])
        .limit(limit * 3)  # Get more to filter by metric availability
        .to_list()
    )

    # Extract metric values from calib_data
    history_items: list[MetricHistoryItem] = []

    for exec_doc in executions:
        calib_data = exec_doc.calib_data

        if "coupling" in calib_data and coupling_id in calib_data["coupling"]:
            coupling_data = calib_data["coupling"][coupling_id]

            if metric in coupling_data:
                metric_data = coupling_data[metric]

                # Handle both dict and direct value formats
                if isinstance(metric_data, dict):
                    value = metric_data.get("value")
                    task_id = metric_data.get("task_id")
                    calibrated_at = metric_data.get("calibrated_at")
                else:
                    value = metric_data
                    task_id = None
                    calibrated_at = None

                # Only include if value exists
                if value is not None:
                    history_items.append(
                        MetricHistoryItem(
                            value=value,
                            execution_id=exec_doc.execution_id,
                            task_id=task_id,
                            timestamp=exec_doc.start_at,
                            calibrated_at=calibrated_at,
                        )
                    )

                    # Stop once we have enough items
                    if len(history_items) >= limit:
                        break

        # Break execution loop if we have enough items
        if len(history_items) >= limit:
            break

    if not history_items:
        logger.warning(f"No history found for chip={chip_id}, coupling_id={coupling_id}, metric={metric}")

    return QubitMetricHistoryResponse(
        chip_id=chip_id,
        qid=coupling_id,  # Reuse qid field for coupling_id
        metric_name=metric,
        username=username,
        history=history_items,
    )
