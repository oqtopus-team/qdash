"""Tests for routing metric heatmaps to qubits or couplings."""

from unittest.mock import MagicMock

import pytest

from qdash.api.services.chip import ChipService
from qdash.common.config.metrics import load_metrics_config


@pytest.mark.parametrize(
    ("metric", "is_coupling"),
    [
        *((metric, True) for metric in load_metrics_config().coupling_metrics),
        ("qubit_frequency", False),
    ],
)
def test_metric_heatmap_queries_correct_entity_type(metric, is_coupling):
    repository = MagicMock()
    repository.aggregate_metric_heatmap.return_value = {
        "values": {"0-1": 0.005},
        "unit": "GHz",
    }
    service = ChipService(repository, MagicMock(), MagicMock())

    result = service.get_metric_heatmap("project-1", "chip-1", metric)

    repository.aggregate_metric_heatmap.assert_called_once_with(
        project_id="project-1", chip_id="chip-1", metric=metric, is_coupling=is_coupling
    )
    assert result is not None
    assert result.values == {"0-1": 0.005}
    assert result.unit == "GHz"
