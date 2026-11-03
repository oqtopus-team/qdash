"""Metrics configuration loader."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


class ColorRange(BaseModel):
    """Default heatmap color range for a metric, in raw (unscaled) units."""

    min: float
    max: float

    @model_validator(mode="after")
    def _check_order(self) -> ColorRange:
        if not self.min < self.max:
            msg = f"color_range.min ({self.min}) must be less than color_range.max ({self.max})"
            raise ValueError(msg)
        return self


class MetricMetadata(BaseModel):
    """Metadata for a single metric."""

    title: str
    unit: str
    scale: float
    description: str | None = None
    evaluation: EvaluationConfig
    threshold: ThresholdConfig | None = None
    color_range: ColorRange | None = None


class ColorScaleConfig(BaseModel):
    """Ordered palette shared by every metric heatmap, low to high."""

    colors: list[str] = Field(min_length=2)


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
    color_scale: ColorScaleConfig
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
