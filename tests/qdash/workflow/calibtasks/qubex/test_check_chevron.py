"""Tests for the fixed-grid CheckChevron task."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_chevron import CheckChevron

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any


class _DummyExperiment:
    def __init__(self) -> None:
        self.params = SimpleNamespace(readout_amplitude={"Q00": 0.0})
        self.modified_frequency_calls: list[dict[str, float]] = []

    def get_qubit_label(self, qid: int) -> str:
        assert qid == 0
        return "Q00"

    def modified_frequencies(self, frequencies: dict[str, float]):
        self.modified_frequency_calls.append(frequencies)
        return nullcontext()


def _configured_task() -> CheckChevron:
    task = CheckChevron()
    task.input_parameters["control_frequency"] = InputParameterModel(value=4.25, unit="GHz")
    task.input_parameters["readout_frequency"] = InputParameterModel(value=6.1, unit="GHz")
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.031, unit="a.u.")
    task.input_parameters["control_amplitude"] = InputParameterModel(value=0.07, unit="a.u.")
    return task


def test_check_chevron_run_executes_one_fixed_grid_sweep(monkeypatch) -> None:
    task = _configured_task()
    experiment = _DummyExperiment()
    captured: dict[str, Any] = {}
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": {"Q00": 4.321},
            "omega_rabis": {"Q00": 0.01},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": {"Q00": 8.5},
        },
        figures={},
    )

    def fake_estimate_qubit_frequency_from_chevron(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return raw_result

    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_chevron."
        "estimate_qubit_frequency_from_chevron",
        fake_estimate_qubit_frequency_from_chevron,
    )

    result = task.run(backend=cast("QubexBackend", object()), qid="0")

    assert result.raw_result.data["resonant_frequencies"]["Q00"] == 4.321
    assert result.r2 is None
    assert experiment.modified_frequency_calls == [{"Q00": 4.25, "RQ00": 6.1}]
    assert experiment.params.readout_amplitude["Q00"] == 0.031
    assert captured["exp"] is experiment
    assert captured["targets"] == ["Q00"]
    assert captured["frequencies"] == {"Q00": 4.25}
    assert captured["amplitudes"] == {"Q00": 0.07}
    np.testing.assert_allclose(captured["detuning_range"], np.linspace(-0.05, 0.05, 41))
    np.testing.assert_allclose(captured["time_range"], np.linspace(0, 250, 26))
    assert captured["n_shots"] == 256
    assert captured["shot_interval"] == 153600.0
    assert captured["plot"] is False
    assert captured["save_image"] is False


def test_check_chevron_postprocess_extracts_frequency_and_figures(monkeypatch) -> None:
    task = _configured_task()
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": {"Q00": 4.321},
            "omega_rabis": {"Q00": 0.01},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": {"Q00": 8.5},
        },
        figures={
            "Q00_measurement": go.Figure(),
            "Q00_transform": go.Figure(),
        },
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.output_parameters["qubit_frequency"].value == 4.321
    assert result.output_parameters["control_amplitude"].value == pytest.approx(0.0875)
    assert result.output_parameters["qubit_frequency"].execution_id == "exec-1"
    assert result.output_parameters["control_amplitude"].execution_id == "exec-1"
    assert len(result.figures) == 3
    assert result.validation_error is None


def test_check_chevron_requires_calibrated_control_frequency(monkeypatch) -> None:
    task = _configured_task()
    task.input_parameters["control_frequency"] = InputParameterModel(value=None)
    monkeypatch.setattr(task, "get_experiment", lambda _backend: _DummyExperiment())

    with pytest.raises(ValueError, match="control_frequency input parameter is required"):
        task.run(backend=cast("QubexBackend", object()), qid="0")


@pytest.mark.parametrize(
    ("omega_rabi", "expected_amplitude"),
    [
        (0.0001, 1.0),
        (10.0, 1e-4),
    ],
)
def test_check_chevron_clips_estimated_control_amplitude(
    monkeypatch, omega_rabi: float, expected_amplitude: float
) -> None:
    task = _configured_task()
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": {"Q00": 4.321},
            "omega_rabis": {"Q00": omega_rabi},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": {"Q00": 8.5},
        },
        figures={},
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.output_parameters["control_amplitude"].value == expected_amplitude
    assert result.validation_error is None


@pytest.mark.parametrize(
    ("ratios", "error"),
    [
        ({"Q00": 4.99}, "below minimum 5.0"),
        ({}, "peak/background RMS ratio for Q00 is missing"),
        ({"Q00": float("nan")}, "peak/background RMS ratio for Q00 is non-finite"),
    ],
)
def test_check_chevron_rejects_invalid_peak_background_rms_ratio(
    monkeypatch, ratios: dict[str, float], error: str
) -> None:
    task = _configured_task()
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": {"Q00": 4.321},
            "omega_rabis": {"Q00": 0.01},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": ratios,
        },
        figures={},
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.validation_error is not None
    assert error in result.validation_error


def test_check_chevron_rejects_zero_rabi_frequency(monkeypatch) -> None:
    task = _configured_task()
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": {"Q00": 4.321},
            "omega_rabis": {"Q00": 0.0},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": {"Q00": 8.5},
        },
        figures={},
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.output_parameters["control_amplitude"].value is None
    assert result.validation_error == "CheckChevron Rabi frequency for Q00 must be positive: 0.0"


@pytest.mark.parametrize("threshold", [-0.1, float("nan"), float("inf"), "invalid"])
def test_check_chevron_rejects_invalid_peak_background_rms_ratio_threshold(
    monkeypatch: pytest.MonkeyPatch,
    threshold: object,
) -> None:
    task = _configured_task()
    task.run_parameters["minimum_peak_background_rms_ratio"].value = cast("Any", threshold)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": {"Q00": 4.321},
            "omega_rabis": {"Q00": 0.01},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": {"Q00": 8.5},
        },
        figures={},
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.validation_error is not None
    assert "minimum_peak_background_rms_ratio" in result.validation_error


@pytest.mark.parametrize("target_omega_rabi", [-0.1, 0.0, float("nan"), float("inf"), "invalid"])
def test_check_chevron_rejects_invalid_target_omega_rabi(
    monkeypatch: pytest.MonkeyPatch,
    target_omega_rabi: object,
) -> None:
    task = _configured_task()
    task.run_parameters["target_omega_rabi"].value = cast("Any", target_omega_rabi)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": {"Q00": 4.321},
            "omega_rabis": {"Q00": 0.01},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": {"Q00": 8.5},
        },
        figures={},
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.output_parameters["control_amplitude"].value is None
    assert result.validation_error is not None
    assert "target_omega_rabi" in result.validation_error


@pytest.mark.parametrize(
    ("resonant_frequencies", "expected_error", "expected_output"),
    [
        ({}, "qubit frequency for Q00 is missing", None),
        ({"Q00": float("nan")}, "qubit frequency for Q00 is non-finite", None),
        ({"Q00": "invalid"}, "qubit frequency for Q00 is not numeric", None),
        ({"Q00": 2.49}, "qubit frequency for Q00 is below minimum 2.5", 2.49),
    ],
)
def test_check_chevron_rejects_invalid_qubit_frequency(
    monkeypatch: pytest.MonkeyPatch,
    resonant_frequencies: dict[str, object],
    expected_error: str,
    expected_output: float | None,
) -> None:
    task = _configured_task()
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={
            "resonant_frequencies": resonant_frequencies,
            "omega_rabis": {"Q00": 0.01},
            "amplitudes_used": {"Q00": 0.07},
            "peak_background_rms_ratios": {"Q00": 8.5},
        },
        figures={"Q00_measurement": go.Figure()},
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.output_parameters["qubit_frequency"].value == expected_output
    assert result.validation_error is not None
    assert expected_error in result.validation_error


def test_check_chevron_rejects_unsupported_result_type(monkeypatch) -> None:
    task = _configured_task()
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    with pytest.raises(
        TypeError,
        match="estimate_qubit_frequency_from_chevron returned unsupported data type",
    ):
        task.postprocess(
            backend=cast("QubexBackend", object()),
            execution_id="exec-1",
            run_result=RunResult(raw_result=object()),
            qid="0",
        )
