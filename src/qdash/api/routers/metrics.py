"""Metrics API router for chip calibration metrics visualization."""

from __future__ import annotations

import logging
from typing import Annotated, Any

import pendulum
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from qdash.api.lib.auth import get_optional_current_user
from qdash.api.schemas.auth import User
from qdash.dbmodel.chip import ChipDocument

router = APIRouter()
logger = logging.getLogger(__name__)


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


def extract_qubit_metrics(chip: ChipDocument, within_hours: int | None = None) -> QubitMetrics:
    """Extract qubit metrics from ChipDocument.

    Args:
    ----
        chip: The chip document
        within_hours: Optional time filter in hours (e.g., 24 for last 24 hours)

    Returns:
    -------
        QubitMetrics with all qubit-level metrics

    """
    # Field mapping from DB to display names
    field_map = {
        "bare_frequency": "qubit_frequency",
        "anharmonicity": "anharmonicity",
        "t1": "t1",
        "t2_echo": "t2_echo",
        "t2_star": "t2_star",
        "average_readout_fidelity": "average_readout_fidelity",
        "x90_gate_fidelity": "x90_gate_fidelity",
        "x180_gate_fidelity": "x180_gate_fidelity",
    }

    # Determine cutoff time if filtering
    cutoff_time = None
    if within_hours:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=within_hours)

    # Initialize metric dictionaries
    metrics_data: dict[str, dict[str, MetricValue]] = {display_name: {} for display_name in field_map.values()}

    # Extract data from each qubit
    for qid, qubit_model in chip.qubits.items():
        if qubit_model.data and isinstance(qubit_model.data, dict):
            for param_name, param_data in qubit_model.data.items():
                if isinstance(param_data, dict) and "value" in param_data:
                    # Check time filter
                    include_param = True
                    if within_hours and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
                            include_param = calibrated_at >= cutoff_time
                        except Exception:
                            include_param = False

                    if include_param and param_name in field_map:
                        display_name = field_map[param_name]
                        value = param_data.get("value")
                        task_id = param_data.get("task_id", "")
                        execution_id = param_data.get("execution_id", "")

                        # Store the value with metadata
                        metrics_data[display_name][qid] = MetricValue(
                            value=value,
                            task_id=task_id if task_id else None,
                            execution_id=execution_id if execution_id else None,
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


def extract_coupling_metrics(chip: ChipDocument, within_hours: int | None = None) -> CouplingMetrics:
    """Extract coupling metrics from ChipDocument.

    Args:
    ----
        chip: The chip document
        within_hours: Optional time filter in hours

    Returns:
    -------
        CouplingMetrics with all coupling-level metrics

    """
    field_map = {
        "zx90_gate_fidelity": "zx90_gate_fidelity",
        "bell_state_fidelity": "bell_state_fidelity",
        "static_zz_interaction": "static_zz_interaction",
    }

    cutoff_time = None
    if within_hours:
        cutoff_time = pendulum.now("Asia/Tokyo").subtract(hours=within_hours)

    # Initialize metric dictionaries
    metrics_data: dict[str, dict[str, MetricValue]] = {display_name: {} for display_name in field_map.values()}

    # Extract data from each coupling
    for coupling_id, coupling_model in chip.couplings.items():
        if coupling_model.data and isinstance(coupling_model.data, dict):
            for param_name, param_data in coupling_model.data.items():
                if isinstance(param_data, dict) and "value" in param_data:
                    # Check time filter
                    include_param = True
                    if within_hours and "calibrated_at" in param_data:
                        try:
                            calibrated_at = pendulum.parse(param_data["calibrated_at"], tz="Asia/Tokyo")
                            include_param = calibrated_at >= cutoff_time
                        except Exception:
                            include_param = False

                    if include_param and param_name in field_map:
                        display_name = field_map[param_name]
                        value = param_data.get("value")
                        task_id = param_data.get("task_id", "")
                        execution_id = param_data.get("execution_id", "")

                        # Store the value with metadata
                        metrics_data[display_name][coupling_id] = MetricValue(
                            value=value,
                            task_id=task_id if task_id else None,
                            execution_id=execution_id if execution_id else None,
                        )

    return CouplingMetrics(
        zx90_gate_fidelity=metrics_data.get("zx90_gate_fidelity") or None,
        bell_state_fidelity=metrics_data.get("bell_state_fidelity") or None,
        static_zz_interaction=metrics_data.get("static_zz_interaction") or None,
    )


@router.get("/chip/{chip_id}/metrics", response_model=ChipMetricsResponse)
async def get_chip_metrics(
    chip_id: str,
    within_hours: Annotated[int | None, Query(description="Filter to data within N hours (e.g., 24)")] = None,
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
    qubit_metrics = extract_qubit_metrics(chip, within_hours)
    coupling_metrics = extract_coupling_metrics(chip, within_hours)

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
