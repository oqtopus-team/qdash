"""Tests for the metrics configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from qdash.common.config.loader import ConfigLoader
from qdash.common.config.metrics import (
    ColorRange,
    MetricMetadata,
    MetricsConfig,
    ThresholdConfig,
    ThresholdRange,
    clear_metrics_config_cache,
    load_metrics_config,
)


def _metric(**extra: object) -> dict[str, object]:
    return {
        "title": "T1",
        "unit": "μs",
        "scale": 1,
        "evaluation": {"mode": "maximize"},
        **extra,
    }


def _metadata(**extra: object) -> MetricMetadata:
    return MetricMetadata.model_validate(_metric(**extra))


def test_color_range_is_optional() -> None:
    metadata = _metadata()
    assert metadata.color_range is None


def test_color_range_parses_in_raw_units() -> None:
    metadata = _metadata(color_range={"min": 0.9, "max": 0.999})
    assert metadata.color_range == ColorRange(min=0.9, max=0.999)


@pytest.mark.parametrize("bounds", [{"min": 5, "max": 5}, {"min": 10, "max": 1}])
def test_color_range_rejects_non_increasing_bounds(bounds: dict[str, float]) -> None:
    with pytest.raises(ValidationError, match=r"color_range\.min"):
        _metadata(color_range=bounds)


def test_color_scale_requires_at_least_two_colors() -> None:
    with pytest.raises(ValidationError):
        MetricsConfig.model_validate(
            {"qubit_metrics": {}, "coupling_metrics": {}, "color_scale": {"colors": ["#000000"]}}
        )


@pytest.mark.parametrize(
    ("group", "key", "expected"),
    [
        (
            "qubit_metrics",
            "average_readout_fidelity",
            ThresholdConfig(value=0.99, range=ThresholdRange(min=0.9, max=1.0, step=0.001)),
        ),
        (
            "qubit_metrics",
            "average_gate_fidelity",
            ThresholdConfig(value=0.999, range=ThresholdRange(min=0.9, max=1.0, step=0.0001)),
        ),
        (
            "qubit_metrics",
            "x90_gate_fidelity",
            ThresholdConfig(value=0.999, range=ThresholdRange(min=0.9, max=1.0, step=0.0001)),
        ),
        (
            "qubit_metrics",
            "x180_gate_fidelity",
            ThresholdConfig(value=0.999, range=ThresholdRange(min=0.9, max=1.0, step=0.0001)),
        ),
        (
            "coupling_metrics",
            "zx90_gate_fidelity",
            ThresholdConfig(value=0.99, range=ThresholdRange(min=0.9, max=1.0, step=0.001)),
        ),
        (
            "coupling_metrics",
            "bell_state_fidelity",
            ThresholdConfig(value=0.95, range=ThresholdRange(min=0.8, max=1.0, step=0.001)),
        ),
    ],
)
def test_fidelity_threshold_range_reaches_one(
    monkeypatch: pytest.MonkeyPatch, group: str, key: str, expected: ThresholdConfig
) -> None:
    """The histogram threshold slider can select 100% fidelity (0% error), see issue #594."""
    monkeypatch.setattr(ConfigLoader, "_CONFIG_DIR", ConfigLoader.LOCAL_CONFIG_DIR)
    ConfigLoader.clear_cache()
    clear_metrics_config_cache()
    try:
        config = load_metrics_config()
    finally:
        ConfigLoader.clear_cache()
        clear_metrics_config_cache()

    metrics = config.qubit_metrics if group == "qubit_metrics" else config.coupling_metrics
    assert metrics[key].threshold == expected
