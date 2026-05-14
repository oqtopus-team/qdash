"""Metrics configuration loader."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel

from qdash.common.config.loader import ConfigLoader


class EvaluationConfig(BaseModel):
    """Evaluation configuration for a metric."""

    mode: Literal["maximize", "minimize", "none"]


class ThresholdRange(BaseModel):
    """Range configuration for threshold slider."""

    min: float
    max: float
    step: float


class ThresholdConfig(BaseModel):
    """Threshold configuration for a metric."""

    value: float
    range: ThresholdRange


class MetricMetadata(BaseModel):
    """Metadata for a single metric."""

    title: str
    unit: str
    scale: float
    description: str | None = None
    evaluation: EvaluationConfig
    threshold: ThresholdConfig | None = None


class CdfGroup(BaseModel):
    """CDF chart group configuration."""

    id: str
    title: str
    unit: str
    metrics: list[str]


class CdfGroupsConfig(BaseModel):
    """CDF groups configuration by metric type."""

    qubit: list[CdfGroup] = []
    coupling: list[CdfGroup] = []


class MetricsConfig(BaseModel):
    """Complete metrics configuration."""

    qubit_metrics: dict[str, MetricMetadata]
    coupling_metrics: dict[str, MetricMetadata]
    color_scale: dict[str, Any]
    cdf_groups: CdfGroupsConfig = CdfGroupsConfig()


@lru_cache(maxsize=1)
def load_metrics_config() -> MetricsConfig:
    """Load metrics configuration from YAML file."""
    data = ConfigLoader.load_metrics()
    try:
        return MetricsConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid metrics configuration: {e}") from e


def clear_metrics_config_cache() -> None:
    """Clear the cached metrics configuration."""
    load_metrics_config.cache_clear()


def get_qubit_metric_metadata(metric_key: str) -> MetricMetadata | None:
    """Get metadata for a qubit metric."""
    return load_metrics_config().qubit_metrics.get(metric_key)


def get_coupling_metric_metadata(metric_key: str) -> MetricMetadata | None:
    """Get metadata for a coupling metric."""
    return load_metrics_config().coupling_metrics.get(metric_key)
