"""Tests for workflow metric normalization and filtering."""

from types import SimpleNamespace

import pytest

from qdash.workflow.service.results import (
    OneQubitResult,
    QubitCalibData,
    normalize_metric_value,
)
from qdash.workflow.service.steps.bringup import BringUp
from qdash.workflow.service.steps.one_qubit import OneQubitFineTune
from qdash.workflow.service.steps.two_qubit import TwoQubitCalibration


@pytest.mark.parametrize(
    ("parameter", "expected"),
    [
        (0.97, 0.97),
        ({"value": 0.98, "error": 0.01}, 0.98),
        (SimpleNamespace(value=0.99), 0.99),
        ({"value": None}, None),
        (None, None),
    ],
)
def test_normalize_metric_value_supports_execution_boundary_formats(
    parameter: object, expected: float | None
) -> None:
    assert normalize_metric_value(parameter) == expected


def test_normalize_metric_value_rejects_non_numeric_value() -> None:
    with pytest.raises(ValueError, match="Metric value must be numeric"):
        normalize_metric_value({"value": {"nested": 0.99}})


def test_one_qubit_fine_tune_filters_serialized_fidelity() -> None:
    raw_results = {
        "Box_A": {
            "0": {
                "status": "success",
                "X90InterleavedRandomizedBenchmarking": {
                    "x90_gate_fidelity": {"value": 0.95, "error": 0.01}
                },
            },
            "1": {
                "status": "success",
                "X90InterleavedRandomizedBenchmarking": {
                    "x90_gate_fidelity": {"value": 0.85, "error": 0.02}
                },
            },
        }
    }

    result = OneQubitFineTune()._build_result(raw_results)

    assert result.get_metric("0", "x90_fidelity") == 0.95
    assert result.filter_by_metric("x90_fidelity", 0.9) == ["0"]


def test_bringup_normalizes_serialized_metrics() -> None:
    metrics = BringUp()._extract_metrics(
        {
            "CheckResonatorSpectroscopy": {
                "readout_frequency": {"value": 7.1},
                "readout_amplitude": SimpleNamespace(value=0.25),
            },
            "CheckQubitSpectroscopy": {
                "coarse_qubit_frequency": {"value": 5.2},
                "anharmonicity": -0.3,
            },
            "CheckChevron": {"qubit_frequency": {"value": 5.15}},
        }
    )

    assert metrics == {
        "readout_frequency": 7.1,
        "readout_amplitude": 0.25,
        "coarse_qubit_frequency": 5.2,
        "anharmonicity": -0.3,
        "qubit_frequency": 5.15,
    }


def test_two_qubit_calibration_normalizes_serialized_metrics() -> None:
    metrics = TwoQubitCalibration()._extract_metrics(
        {
            "ZX90InterleavedRandomizedBenchmarking": {"zx90_gate_fidelity": {"value": 0.94}},
            "CheckBellState": {"bell_fidelity": SimpleNamespace(value=0.91)},
            "Check2QGateCoherenceLimit": {"two_qubit_gate_coherence_limit": 0.89},
        }
    )

    assert metrics == {
        "zx90_fidelity": 0.94,
        "bell_fidelity": 0.91,
        "two_qubit_gate_coherence_limit": 0.89,
    }


def test_filter_by_metric_ignores_missing_metrics() -> None:
    result = OneQubitResult(
        qubits={
            "0": QubitCalibData(status="success", metrics={"fidelity": 0.95}),
            "1": QubitCalibData(status="success"),
        }
    )

    assert result.filter_by_metric("fidelity", 0.9) == ["0"]
