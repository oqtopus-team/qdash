"""Tests for routing metric heatmaps to qubits or couplings."""

from unittest.mock import MagicMock

import pytest

from qdash.api.services.chip import ChipService


@pytest.mark.parametrize(
    ("metric", "is_coupling"),
    [
        ("qubit_qubit_coupling_strength", True),
        ("static_zz_interaction", True),
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
