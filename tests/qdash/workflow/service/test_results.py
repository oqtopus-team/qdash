"""Tests for workflow metric normalization and filtering."""

from types import SimpleNamespace

import pytest

from qdash.workflow.service.results import (
    OneQubitResult,
    QubitCalibData,
    normalize_metric_value,
)
from qdash.workflow.service.steps.bringup import BringUp
from qdash.workflow.service.steps.one_qubit import OneQubitCheck, OneQubitFineTune
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


def ok(name: str, call_id: str | None = None, **output: object) -> dict[str, object]:
    return {
        "call_id": call_id or name,
        "name": name,
        "status": "success",
        "task_id": f"task-{call_id or name}",
        "output": output,
    }


def failed(name: str, call_id: str | None = None) -> dict[str, object]:
    return {"call_id": call_id or name, "name": name, "status": "failed", "error": "bad fit"}


def target(*calls: dict[str, object]) -> dict[str, object]:
    status = "failed" if any(call["status"] == "failed" for call in calls) else "success"
    return {"status": status, "calls": list(calls)}


def test_one_qubit_fine_tune_filters_serialized_fidelity() -> None:
    raw_results = {
        "Box_A": {
            "0": target(
                ok(
                    "X90InterleavedRandomizedBenchmarking",
                    x90_gate_fidelity={"value": 0.95, "error": 0.01},
                )
            ),
            "1": target(
                ok(
                    "X90InterleavedRandomizedBenchmarking",
                    x90_gate_fidelity={"value": 0.85, "error": 0.02},
                )
            ),
        }
    }

    result = OneQubitFineTune()._build_result(raw_results)

    assert result.step_id == "one_qubit_fine_tune"
    assert result.get_metric("0", "x90_fidelity") == 0.95
    assert result.filter_by_metric("x90_fidelity", 0.9) == ["0"]


def test_step_metrics_use_the_latest_call_of_a_task_without_fallback() -> None:
    raw = target(
        ok("CheckT1Average", "t1_coarse", t1_average={"value": 50.0}),
        failed("CheckT1Average", "t1_fine"),
    )

    # The fine call failed; the coarse call's good value must not stand in for it.
    assert OneQubitCheck()._extract_metrics(raw) == {}
    raw_ok = target(
        ok("CheckT1Average", "t1_coarse", t1_average={"value": 50.0}),
        ok("CheckT1Average", "t1_fine", t1_average={"value": 42.0}),
    )
    assert OneQubitCheck()._extract_metrics(raw_ok) == {"t1_average": 42.0}


def test_calls_are_ordered_and_addressable_by_call_id() -> None:
    data = QubitCalibData(
        status="failed",
        raw=target(
            ok("CheckRamsey", "ramsey_coarse", t2_star={"value": 20.0}),
            failed("CheckRamsey", "ramsey_fine"),
        ),
    )

    assert [call.call_id for call in data.calls] == ["ramsey_coarse", "ramsey_fine"]
    assert [call.call_id for call in data.calls_of("CheckRamsey")] == [
        "ramsey_coarse",
        "ramsey_fine",
    ]
    assert data.latest_call("CheckRamsey").call_id == "ramsey_fine"  # type: ignore[union-attr]
    assert data.call("ramsey_coarse").task_id == "task-ramsey_coarse"  # type: ignore[union-attr]
    assert data.call_metric("ramsey_coarse", "t2_star") == 20.0
    assert data.call_metric("ramsey_fine", "t2_star") is None
    assert data.call("missing") is None


def test_call_metric_filter_excludes_failed_calls_instead_of_falling_back() -> None:
    result = OneQubitResult(
        qubits={
            "0": QubitCalibData(
                status="failed",
                raw=target(
                    ok("CheckRamsey", "ramsey_coarse", t2_star={"value": 30.0}),
                    failed("CheckRamsey", "ramsey_fine"),
                ),
            ),
            "1": QubitCalibData(
                status="success",
                raw=target(
                    ok("CheckRamsey", "ramsey_coarse", t2_star={"value": 1.0}),
                    ok("CheckRamsey", "ramsey_fine", t2_star={"value": 25.0}),
                ),
            ),
        }
    )

    assert result.filter_by_call_metric("ramsey_fine", "t2_star", 10.0) == ["1"]
    assert result.filter_by_call_metric("ramsey_coarse", "t2_star", 10.0) == ["0"]
    assert result.call_succeeded_qids("ramsey_fine") == ["1"]
    assert result.call_succeeded_qids("ramsey_coarse") == ["0", "1"]


def test_bringup_normalizes_serialized_metrics() -> None:
    metrics = BringUp()._extract_metrics(
        target(
            ok(
                "CheckResonatorSpectroscopy",
                readout_frequency={"value": 7.1},
                readout_amplitude=SimpleNamespace(value=0.25),
            ),
            ok(
                "CheckQubitSpectroscopy",
                coarse_qubit_frequency={"value": 5.2},
                qubit_anharmonicity=-0.3,
            ),
            ok("CheckAdaptiveChevron", qubit_frequency={"value": 5.15}),
        )
    )

    assert metrics == {
        "readout_frequency": 7.1,
        "readout_amplitude": 0.25,
        "coarse_qubit_frequency": 5.2,
        "qubit_frequency": 5.15,
    }


def test_two_qubit_calibration_normalizes_serialized_metrics() -> None:
    metrics = TwoQubitCalibration()._extract_metrics(
        target(
            ok("ZX90InterleavedRandomizedBenchmarking", zx90_gate_fidelity={"value": 0.94}),
            ok("CheckBellState", bell_fidelity=SimpleNamespace(value=0.91)),
            ok("Check2QGateCoherenceLimit", two_qubit_gate_coherence_limit=0.89),
        )
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
