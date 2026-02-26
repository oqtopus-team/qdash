"""Metrics API router for chip calibration metrics visualization."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from qdash.api.dependencies import get_metrics_service  # noqa: TCH002
from qdash.api.lib.metrics_config import load_metrics_config
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
)
from qdash.api.schemas.metrics import (
    ChipMetricsResponse,
    QubitMetricHistoryResponse,
)
from qdash.api.services.metrics_service import MetricsService  # noqa: TCH002

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.get(
    "/chips/{chip_id}/metrics", response_model=ChipMetricsResponse, operation_id="getChipMetrics"
)
async def get_chip_metrics(
    chip_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    metrics_service: Annotated[MetricsService, Depends(get_metrics_service)],
    within_hours: Annotated[
        int | None, Query(description="Filter to data within N hours (e.g., 24)")
    ] = None,
    selection_mode: Annotated[
        Literal["latest", "best", "average"],
        Query(
            description=(
                "Selection mode: 'latest' for most recent, "
                "'best' for optimal, 'average' for mean values"
            )
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
        metrics_service: Injected metrics service
        within_hours: Optional filter to only include data from last N hours (e.g., 24)
        selection_mode: "latest" to get most recent values, "best" to get optimal values

    Returns:
    -------
        ChipMetricsResponse with all metrics data

    """
    return metrics_service.get_chip_metrics(
        chip_id=chip_id,
        project_id=ctx.project_id,
        username=ctx.user.username,
        within_hours=within_hours,
        selection_mode=selection_mode,
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
    metrics_service: Annotated[MetricsService, Depends(get_metrics_service)],
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
        metrics_service: Injected metrics service
        metric: Metric name to retrieve history for
        limit: Maximum number of history items (None for unlimited within time range)
        within_days: Optional filter to only include data from last N days

    Returns:
    -------
        QubitMetricHistoryResponse with historical metric data and task_ids

    """
    return metrics_service.get_metric_history(
        chip_id=chip_id,
        qid=qid,
        project_id=ctx.project_id,
        username=ctx.user.username,
        metric=metric,
        entity_type="qubit",
        limit=limit,
        within_days=within_days,
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
    metrics_service: Annotated[MetricsService, Depends(get_metrics_service)],
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
        metrics_service: Injected metrics service
        metric: Metric name to retrieve history for
        limit: Maximum number of history items (None for unlimited within time range)
        within_days: Optional filter to only include data from last N days

    Returns:
    -------
        QubitMetricHistoryResponse with historical metric data and task_ids
        (Note: qid field contains coupling_id for coupling metrics)

    """
    return metrics_service.get_metric_history(
        chip_id=chip_id,
        qid=coupling_id,
        project_id=ctx.project_id,
        username=ctx.user.username,
        metric=metric,
        entity_type="coupling",
        limit=limit,
        within_days=within_days,
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
    metrics_service: Annotated[MetricsService, Depends(get_metrics_service)],
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
    pdf_buffer, filename, _ = metrics_service.generate_metrics_pdf(
        chip_id=chip_id,
        project_id=ctx.project_id,
        username=ctx.user.username,
        within_hours=within_hours,
        selection_mode=selection_mode,
    )

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
