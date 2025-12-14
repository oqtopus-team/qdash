"""Metrics configuration loader.

This module loads metrics metadata from YAML configuration file.
The configuration provides display metadata (titles, units, scales) for metrics.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel


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
    """Load metrics configuration from YAML file.

    Returns
    -------
        MetricsConfig with all metric metadata

    Raises
    ------
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is invalid

    Priority order for config file:
        1. METRICS_CONFIG_PATH environment variable (highest priority)
        2. /app/config/custom/metrics.yaml (Docker custom)
        3. config/custom/metrics.yaml (local custom)
        4. /app/config/metrics.yaml (Docker default)
        5. config/metrics.yaml (local default)

    """
    import os

    project_root = Path(__file__).parent.parent.parent.parent.parent

    # Try multiple possible locations for the config file (in priority order)
    possible_paths = [
        # 1. Environment variable override (highest priority)
        Path(os.getenv("METRICS_CONFIG_PATH", "")) if os.getenv("METRICS_CONFIG_PATH") else None,
        # 2. Custom configuration in config/custom/ (Docker environment)
        Path("/app/config/custom/metrics.yaml"),
        # 3. Custom configuration in config/custom/ (local development)
        project_root / "config" / "custom" / "metrics.yaml",
        # 4. Docker environment: mounted at /app/config
        Path("/app/config/metrics.yaml"),
        # 5. Local development: default config
        project_root / "config" / "metrics.yaml",
    ]

    config_path = None
    for path in possible_paths:
        if path and path.exists():
            config_path = path
            break

    if not config_path:
        raise FileNotFoundError(
            f"Metrics config file not found. Tried: {[str(p) for p in possible_paths if p]}"
        )

    with open(config_path) as f:
        data = yaml.safe_load(f)

    try:
        return MetricsConfig(**data)
    except Exception as e:
        raise ValueError(f"Invalid metrics configuration: {e}") from e


def get_qubit_metric_metadata(metric_key: str) -> MetricMetadata | None:
    """Get metadata for a qubit metric.

    Args:
    ----
        metric_key: The metric key (e.g., 't1', 'qubit_frequency')

    Returns:
    -------
        MetricMetadata if found, None otherwise

    """
    config = load_metrics_config()
    return config.qubit_metrics.get(metric_key)


def get_coupling_metric_metadata(metric_key: str) -> MetricMetadata | None:
    """Get metadata for a coupling metric.

    Args:
    ----
        metric_key: The metric key (e.g., 'zx90_gate_fidelity')

    Returns:
    -------
        MetricMetadata if found, None otherwise

    """
    config = load_metrics_config()
    return config.coupling_metrics.get(metric_key)
