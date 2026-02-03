"""Schema definitions for metrics router."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
    timestamp: datetime
    calibrated_at: datetime | None = None
    name: str | None = None
    input_parameters: dict[str, Any] | None = None
    output_parameters: dict[str, Any] | None = None


class QubitMetricHistoryResponse(BaseModel):
    """Historical metric data for a single qubit."""

    chip_id: str
    qid: str
    metric_name: str
    username: str
    history: list[MetricHistoryItem]
