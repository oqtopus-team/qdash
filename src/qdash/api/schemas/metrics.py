"""Schema definitions for metrics router."""

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class MetricValue(BaseModel):
    """Single metric value with metadata."""

    value: float | None = None
    task_id: str | None = None
    execution_id: str | None = None
    stddev: float | None = None

    @field_validator("value", "stddev", mode="before")
    @classmethod
    def sanitize_float(cls, v: float | None) -> float | None:
        """Convert non-JSON-compliant floats (inf, nan) to None."""
        if v is not None and not math.isfinite(v):
            return None
        return v


class ChipMetricsResponse(BaseModel):
    """Complete chip metrics response."""

    chip_id: str
    username: str
    qubit_count: int
    within_hours: int | None = None
    qubit_metrics: dict[str, dict[str, MetricValue]]
    coupling_metrics: dict[str, dict[str, MetricValue]]


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
