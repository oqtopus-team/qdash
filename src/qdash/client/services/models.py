from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ChipResponse:
    """OpenAPI schema: ChipResponse."""

    chip_id: str
    size: int = 64
    topology_id: str | None = None
    qubit_count: int = 0
    coupling_count: int = 0
    installed_at: str | None = None
    activity_status: str = "active"
    current_cooldown_id: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChipResponse:
        return cls(
            chip_id=str(raw.get("chip_id") or ""),
            size=int(raw.get("size", 64) or 64),
            topology_id=raw.get("topology_id"),
            qubit_count=int(raw.get("qubit_count", 0) or 0),
            coupling_count=int(raw.get("coupling_count", 0) or 0),
            installed_at=raw.get("installed_at"),
            activity_status=str(raw.get("activity_status") or "active"),
            current_cooldown_id=raw.get("current_cooldown_id"),
        )


@dataclass(slots=True)
class ListChipsResponse:
    """OpenAPI schema: ListChipsResponse."""

    chips: list[ChipResponse]
    total: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ListChipsResponse:
        chips_raw = raw.get("chips")
        chips: list[ChipResponse] = []
        if isinstance(chips_raw, list):
            chips = [ChipResponse.from_dict(item) for item in chips_raw if isinstance(item, dict)]
        return cls(chips=chips, total=int(raw.get("total", len(chips)) or 0))


@dataclass(slots=True)
class ParameterModel:
    """OpenAPI schema: ParameterModel."""

    parameter_name: str = ""
    qid_role: str = ""
    value: float | int = 0
    value_type: str = "float"
    error: float = 0.0
    unit: str = ""
    description: str = ""
    calibrated_at: str | None = None
    execution_id: str = ""
    task_id: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ParameterModel:
        value = raw.get("value", 0)
        if not isinstance(value, (int, float)):
            value = 0
        return cls(
            parameter_name=str(raw.get("parameter_name") or ""),
            qid_role=str(raw.get("qid_role") or ""),
            value=value,
            value_type=str(raw.get("value_type") or "float"),
            error=float(raw.get("error", 0.0) or 0.0),
            unit=str(raw.get("unit") or ""),
            description=str(raw.get("description") or ""),
            calibrated_at=raw.get("calibrated_at"),
            execution_id=str(raw.get("execution_id") or ""),
            task_id=str(raw.get("task_id") or ""),
        )


@dataclass(slots=True)
class TimeSeriesData:
    """OpenAPI schema: TimeSeriesData."""

    data: dict[str, list[ParameterModel]]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TimeSeriesData:
        mapped: dict[str, list[ParameterModel]] = {}
        data_raw = raw.get("data")
        if not isinstance(data_raw, dict):
            return cls(data={})

        for key, points in data_raw.items():
            if not isinstance(points, list):
                continue
            mapped[str(key)] = [
                ParameterModel.from_dict(item) for item in points if isinstance(item, dict)
            ]
        return cls(data=mapped)


@dataclass(slots=True)
class ChipMetricsResponse:
    """OpenAPI schema: ChipMetricsResponse."""

    chip_id: str
    username: str
    qubit_count: int
    within_hours: int | None
    start_at: str | None
    end_at: str | None
    qubit_metrics: dict[str, dict[str, Any]]
    coupling_metrics: dict[str, dict[str, Any]]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChipMetricsResponse:
        qubit_metrics = raw.get("qubit_metrics")
        coupling_metrics = raw.get("coupling_metrics")
        return cls(
            chip_id=str(raw.get("chip_id") or ""),
            username=str(raw.get("username") or ""),
            qubit_count=int(raw.get("qubit_count", 0) or 0),
            within_hours=(
                int(raw["within_hours"]) if raw.get("within_hours") is not None else None
            ),
            start_at=raw.get("start_at"),
            end_at=raw.get("end_at"),
            qubit_metrics=qubit_metrics if isinstance(qubit_metrics, dict) else {},
            coupling_metrics=coupling_metrics if isinstance(coupling_metrics, dict) else {},
        )


@dataclass(slots=True)
class NormalizedMetricRecord:
    """Canonical metric representation used by exporter caches."""

    chip_id: str
    entity_type: str
    entity_id: str
    metric_name: str
    value: float
    unit: str = ""
    observed_at: datetime | None = None
