"""Tests for the metrics configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from qdash.common.config.metrics import ColorRange, MetricMetadata, MetricsConfig


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
