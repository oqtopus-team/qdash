"""Tests for the spin-lock relaxation spectroscopy task."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
import qubex.contrib

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qubex.measurement.check_spin_lock_spectroscopy import (
    CheckSpinLockSpectroscopy,
    SpinLockSpectroscopyData,
)


class _Pulse:
    def __init__(self, params: SimpleNamespace) -> None:
        self.params = params
        self.control_amplitudes_seen: list[float] = []

    def calc_control_amplitude(self, _target: str, frequency: float) -> float:
        self.control_amplitudes_seen.append(float(self.params.control_amplitude["Q00"]))
        return 20.0 * frequency

    def calc_rabi_rate(self, _target: str, amplitude: float) -> float:
        return amplitude / 20.0


class _Experiment:
    def __init__(self) -> None:
        self.params = SimpleNamespace(
            control_amplitude={"Q00": 0.01},
            readout_amplitude={"Q00": 0.0},
        )
        self.pulse = _Pulse(self.params)
        self.modified_frequency_calls: list[dict[str, float]] = []

    def get_qubit_label(self, qid: int) -> str:
        assert qid == 0
        return "Q00"

    def get_resonator_label(self, qid: int) -> str:
        assert qid == 0
        return "RQ00"

    def modified_frequencies(self, frequencies: dict[str, float]):
        self.modified_frequency_calls.append(frequencies)
        return nullcontext()


def _task() -> CheckSpinLockSpectroscopy:
    task = CheckSpinLockSpectroscopy()
    values = {
        "control_amplitude": 0.02,
        "control_frequency": 5.0,
        "readout_frequency": 6.1,
        "readout_amplitude": 0.03,
        "hpi_amplitude": 0.08,
        "hpi_duration": 32.0,
        "t1": 0.0,
        "t2_echo": 0.0,
    }
    for name, value in values.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    task.run_parameters["spin_lock_frequency_range"].value = [0.004, 0.05, 0.1]
    task.run_parameters["spin_lock_frequency_range"].value_type = "list"
    return task


def _target_data(fit_success: np.ndarray | None = None) -> dict[str, Any]:
    success = np.array([True, False]) if fit_success is None else fit_success
    frequencies = np.array([0.004, 0.05])
    durations = np.array([100.0, 200.0, 300.0])
    shape = (frequencies.size, durations.size)
    point_estimates = {
        name: np.ones(shape)
        for name in (
            "a",
            "a_error",
            "a_error_minus",
            "a_error_plus",
            "b",
            "b_error",
            "b_error_minus",
            "b_error_plus",
            "p",
            "p_error",
            "p_error_minus",
            "p_error_plus",
            "k",
            "q",
            "phi",
        )
    }
    data: dict[str, Any] = {
        "duration_range": durations,
        "total_pulse_duration_range": durations + 32.0,
        "ramp_duration": 16.0,
        "requested_rabi_frequencies": frequencies,
        "drive_amplitudes": frequencies * 20.0,
        "rabi_frequencies": frequencies,
        "expectation_labels": ("X+", "Z+", "X-", "Z-", "Xi", "Yi", "Zi"),
        "mean_iq": np.ones((*shape, 7), dtype=np.complex128),
        "expectations": np.ones((*shape, 7)),
        "expectation_errors": np.full((*shape, 7), 0.01),
        "measurement_order": np.tile(np.arange(durations.size * 7), (frequencies.size, 1)),
        "point_estimates": point_estimates,
        "fit_success": success,
        "fit_messages": ["ok" if item else "failed" for item in success],
        "t1_plot_mask": success.copy(),
        "t2_plot_mask": success.copy(),
        "t1_exclusion_messages": [None if item else "failed" for item in success],
        "t2_exclusion_messages": [None if item else "failed" for item in success],
        "min_a0": 0.5,
        "min_b0": 0.5,
        "uncertainty_method": "shot_sem_and_robust_covariance",
    }
    for name in (
        "theta",
        "t1_rho",
        "t2_rho",
        "p_inf",
        "a0",
        "b0",
        "shift",
        "axis_rotation_frequency",
    ):
        data[name] = np.ones(frequencies.size)
        data[f"{name}_error"] = np.full(frequencies.size, 0.1)
    return data


def _qubex_result(fit_success: np.ndarray | None = None) -> Any:
    figures = {
        "Q00_parameter_heatmaps": go.Figure(),
        "Q00_relaxation_spectroscopy": go.Figure(),
    }
    return SimpleNamespace(
        data={"results": {"Q00": _target_data(fit_success)}},
        figures=figures,
    )


def test_run_filters_unreachable_frequencies_and_uses_fallback_durations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    experiment = _Experiment()
    measure = MagicMock(return_value=_qubex_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(qubex.contrib, "spin_lock_relaxation_spectroscopy", measure)

    run_result = task.run(cast("Any", object()), "0")

    payload = run_result.raw_result
    np.testing.assert_allclose(payload.requested_frequencies, [0.004, 0.05, 0.1])
    np.testing.assert_allclose(payload.accepted_frequencies, [0.004, 0.05])
    np.testing.assert_allclose(payload.rejected_frequencies, [0.1])
    kwargs = measure.call_args.kwargs
    np.testing.assert_allclose(kwargs["spin_lock_frequency_range"], [0.004, 0.05])
    np.testing.assert_allclose(kwargs["duration_range"], np.geomspace(100.0, 200e3, 21))
    assert kwargs["t1"] is None
    assert kwargs["t2_echo"] is None
    assert "n_duration_points" not in kwargs
    assert "ramp_duration" not in kwargs
    assert "min_a0" not in kwargs
    assert "min_b0" not in kwargs
    assert kwargs["plot"] is False
    assert kwargs["save_image"] is False
    assert kwargs["enable_tqdm"] is True
    assert experiment.modified_frequency_calls == [{"Q00": 5.0, "RQ00": 6.1}]
    assert experiment.params.control_amplitude["Q00"] == 0.02
    assert experiment.pulse.control_amplitudes_seen == [0.02, 0.02, 0.02]
    assert experiment.params.readout_amplitude["Q00"] == 0.03


def test_run_uses_available_qdash_coherence_time(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    task.input_parameters["t1"] = InputParameterModel(value=80.0)
    experiment = _Experiment()
    measure = MagicMock(return_value=_qubex_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(qubex.contrib, "spin_lock_relaxation_spectroscopy", measure)

    task.run(cast("Any", object()), "0")

    kwargs = measure.call_args.kwargs
    assert kwargs["duration_range"] is None
    assert kwargs["t1"] == 80_000.0
    assert kwargs["t2_echo"] is None


def test_explicit_duration_range_takes_precedence_over_coherence_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    task.input_parameters["t1"] = InputParameterModel(value=80.0)
    task.input_parameters["t2_echo"] = InputParameterModel(value=60.0)
    task.run_parameters["duration_range"].value = [100.0, 300.0, 900.0]
    experiment = _Experiment()
    measure = MagicMock(return_value=_qubex_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(qubex.contrib, "spin_lock_relaxation_spectroscopy", measure)

    task.run(cast("Any", object()), "0")

    kwargs = measure.call_args.kwargs
    np.testing.assert_allclose(kwargs["duration_range"], [100.0, 300.0, 900.0])
    assert kwargs["t1"] is None
    assert kwargs["t2_echo"] is None


def test_run_rejects_frequency_sweep_when_no_point_is_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    task.run_parameters["spin_lock_frequency_range"].value = [0.1, 0.2]
    experiment = _Experiment()
    measure = MagicMock()
    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(qubex.contrib, "spin_lock_relaxation_spectroscopy", measure)

    with pytest.raises(ValueError, match="No requested spin-lock frequency is reachable"):
        task.run(cast("Any", object()), "0")

    measure.assert_not_called()


def test_postprocess_succeeds_when_at_least_one_fit_succeeds() -> None:
    task = _task()
    result = task.postprocess(
        cast("Any", object()),
        "exec",
        RunResult(
            raw_result=SimpleNamespace(
                result=_qubex_result(),
                requested_frequencies=np.array([0.004, 0.05, 0.1]),
                accepted_frequencies=np.array([0.004, 0.05]),
                rejected_frequencies=np.array([0.1]),
            )
        ),
        "0",
    )

    assert result.output_parameters == {}
    assert len(result.figures) == 2
    assert result.validation_error is None


def test_postprocess_fails_when_all_fits_fail_but_keeps_figures() -> None:
    task = _task()
    result = task.postprocess(
        cast("Any", object()),
        "exec",
        RunResult(
            raw_result=SimpleNamespace(
                result=_qubex_result(np.array([False, False])),
                requested_frequencies=np.array([0.004, 0.05, 0.1]),
                accepted_frequencies=np.array([0.004, 0.05]),
                rejected_frequencies=np.array([0.1]),
            )
        ),
        "0",
    )

    assert len(result.figures) == 2
    assert result.validation_error == "Spin-lock relaxation fit failed at all frequencies for Q00."


def test_extract_raw_data_round_trips_all_reanalysis_inputs(tmp_path) -> None:
    task = _task()
    payload = SimpleNamespace(
        result=_qubex_result(),
        requested_frequencies=np.array([0.004, 0.05, 0.1]),
        accepted_frequencies=np.array([0.004, 0.05]),
        rejected_frequencies=np.array([0.1]),
    )

    artifacts = task.extract_raw_data(RunResult(raw_result=payload))

    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert isinstance(artifact, SpinLockSpectroscopyData)
    path = tmp_path / "spin_lock.nc"
    artifact.save_netcdf(path)
    loaded = SpinLockSpectroscopyData.load_netcdf(path)
    assert loaded.target == "Q00"
    np.testing.assert_allclose(loaded.rejected_rabi_frequencies, [0.1])
    np.testing.assert_allclose(loaded.expectations, artifact.expectations)
    np.testing.assert_allclose(loaded.fit_parameters["t1_rho"], [1.0, 1.0])
    assert loaded.fit_messages == ("ok", "failed")
    assert loaded.min_a0 == 0.5
    assert loaded.min_b0 == 0.5


def test_task_default_frequency_range_and_registration() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401

    spec = CheckSpinLockSpectroscopy.run_spec["spin_lock_frequency_range"]
    assert spec.value_type == "np.linspace"
    assert spec.default == (0.004, 0.1, 25)
    assert "n_duration_points" not in CheckSpinLockSpectroscopy.run_spec
    assert "ramp_duration" not in CheckSpinLockSpectroscopy.run_spec
    assert "min_a0" not in CheckSpinLockSpectroscopy.run_spec
    assert "min_b0" not in CheckSpinLockSpectroscopy.run_spec
    assert {"hpi_amplitude", "hpi_duration"} <= set(CheckSpinLockSpectroscopy.input_spec)
    assert not {
        "drag_hpi_amplitude",
        "drag_hpi_duration",
        "drag_hpi_beta",
    } & set(CheckSpinLockSpectroscopy.input_spec)
    assert BaseTask.registry["qubex"]["CheckSpinLockSpectroscopy"] is CheckSpinLockSpectroscopy
