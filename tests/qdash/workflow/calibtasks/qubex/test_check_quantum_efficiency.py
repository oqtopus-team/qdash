"""Tests for the Qubex quantum-efficiency task."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
import qubex.contrib

from qdash.common.config.metrics import load_metrics_config
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qubex.measurement.check_quantum_efficiency import (
    CheckQuantumEfficiency,
    QuantumEfficiencyData,
)


def _task() -> CheckQuantumEfficiency:
    task = CheckQuantumEfficiency()
    values = {
        "control_amplitude": 0.02,
        "rabi_amplitude": 0.02,
        "rabi_phase": 0.0,
        "rabi_offset": 0.0,
        "rabi_angle": 0.0,
        "rabi_noise": 0.01,
        "rabi_distance": 1.0,
        "rabi_reference_phase": 0.0,
        "rabi_r2": 0.99,
        "maximum_rabi_frequency": 100.0,
        "control_frequency": 5.0,
        "readout_frequency": 6.1,
        "readout_amplitude": 0.2,
        "hpi_amplitude": 0.05,
        "hpi_duration": 32.0,
    }
    for name, value in values.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    task.run_parameters["readout_duration"].value = 2048.0
    task.run_parameters["shots"].value = 4096
    task.run_parameters["interval"].value = 204800.0
    return task


def _experiment() -> Any:
    exp = MagicMock()
    exp.params.readout_amplitude = {"Q00": 0.01}
    applied: list[dict[str, float]] = []

    @contextmanager
    def modified_frequencies(values: dict[str, float]):
        applied.append(values)
        yield

    exp.modified_frequencies.side_effect = modified_frequencies
    exp.applied_frequencies = applied
    return exp


def _result(efficiency: float = 0.42) -> Any:
    amplitudes = np.array([0.01, 0.02])
    snr_fit = {
        "a": 2.0,
        "a_err": 0.1,
        "fit_amplitudes": np.array([0.0, 0.01, 0.02]),
        "y_fit": np.array([0.0, 0.02, 0.04]),
    }
    dephasing_fit = {
        "b": 0.48,
        "b_err": 0.01,
        "sigma_m": 0.46,
        "sigma_m_err": 0.02,
        "fit_amplitudes": np.array([0.0, 0.01, 0.02]),
        "rho01_fit": np.array([0.48, 0.47, 0.46]),
    }
    overview = go.Figure()
    return SimpleNamespace(
        data={
            "target": "Q00",
            "readout_amplitudes": amplitudes,
            "quantum_efficiency": efficiency,
            "quantum_efficiency_error": 0.03,
            "pointwise_quantum_efficiency": np.array([np.nan, 0.41]),
            "projection_method": "max_amplitude",
            "projection_weights": np.array([1.0 + 0.5j, 0.2 - 0.1j]),
            "projection_reference_amplitude": 0.02,
            "snr": {
                "values": np.array([0.02, 0.04]),
                "standard_error": np.array([0.001, 0.002]),
                "uncertainty_method": ["fit_covariance", "delta_fallback"],
                "signal": np.array([0.1, 0.2]),
                "noise": np.array([5.0, 5.0]),
            },
            "measurement_induced_dephasing": {
                "rho01": np.array([0.48, 0.46]),
                "rho01_standard_error": np.array([0.01, 0.02]),
                "beta_m_raw": np.array([0.0, 0.04]),
            },
            "snr_fit": snr_fit,
            "measurement_induced_dephasing_fit": dephasing_fit,
            "early_stop_enabled": False,
            "early_stopped": False,
        },
        figure=overview,
        figures={"overview": overview, "snr": go.Figure(), "dephasing": go.Figure()},
    )


def test_run_passes_only_supported_measurement_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    task.run_parameters["amplitude_range"].value = [0.01, 0.05, 0.1]
    exp = _experiment()
    measure = MagicMock(return_value=_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "get_resonator_label", lambda _backend, _qid: "RQ00")
    monkeypatch.setattr(qubex.contrib, "quantum_efficiency_measurement", measure)

    run_result = task.run(cast("Any", object()), "0")

    assert run_result.raw_result is measure.return_value
    assert exp.params.readout_amplitude["Q00"] == 0.2
    assert exp.applied_frequencies == [{"Q00": 5.0, "RQ00": 6.1}]
    kwargs = measure.call_args.kwargs
    assert kwargs["targets"] == "Q00"
    np.testing.assert_allclose(kwargs["amplitude_range"], [0.01, 0.05, 0.1])
    assert kwargs["n_shots"] == 4096
    assert kwargs["shot_interval"] == 204800.0
    assert kwargs["readout_duration"] == 2048.0
    assert kwargs["plot"] is False
    assert kwargs["save_image"] is False
    assert not {
        "phase_range",
        "readout_amplitude",
        "projection_method",
        "early_stop",
        "enable_tqdm",
    } & set(kwargs)


def test_run_uses_qubex_default_amplitude_range_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    exp = _experiment()
    measure = MagicMock(return_value=_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "get_resonator_label", lambda _backend, _qid: "RQ00")
    monkeypatch.setattr(qubex.contrib, "quantum_efficiency_measurement", measure)

    task.run(cast("Any", object()), "0")

    assert measure.call_args.kwargs["amplitude_range"] is None


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("shots", 0, "shots must be positive"),
        ("interval", float("nan"), "interval must be finite and positive"),
        ("readout_duration", 0.0, "readout_duration must be finite and positive"),
        ("amplitude_range", [0.01], "at least two"),
        ("amplitude_range", [0.02, 0.01], "strictly increasing"),
    ],
)
def test_run_rejects_invalid_options(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: Any,
    message: str,
) -> None:
    task = _task()
    task.run_parameters[name].value = value
    measure = MagicMock()
    monkeypatch.setattr(qubex.contrib, "quantum_efficiency_measurement", measure)

    with pytest.raises(ValueError, match=message):
        task.run(cast("Any", SimpleNamespace(get_instance=MagicMock())), "0")

    measure.assert_not_called()


def test_postprocess_keeps_only_overview_and_warns_above_one(
    caplog: pytest.LogCaptureFixture,
) -> None:
    task = _task()

    processed = task.postprocess(
        cast("Any", object()),
        "exec",
        RunResult(raw_result=_result(1.08)),
        "0",
    )

    assert processed.output_parameters["quantum_efficiency"].value == 1.08
    assert processed.output_parameters["quantum_efficiency"].execution_id == "exec"
    assert processed.figures == [_result().figures["overview"]]
    assert len(processed.figures) == 1
    assert processed.validation_error is None
    assert "exceeds the physical bound" in caplog.text


@pytest.mark.parametrize("efficiency", [float("nan"), float("inf"), -0.1])
def test_postprocess_rejects_nonfinite_or_negative_efficiency(efficiency: float) -> None:
    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        RunResult(raw_result=_result(efficiency)),
        "0",
    )

    assert processed.validation_error is not None


def test_extract_raw_data_round_trips_compact_numerical_result(tmp_path: Any) -> None:
    artifact = _task().extract_raw_data(RunResult(raw_result=_result()))[0]

    assert isinstance(artifact, QuantumEfficiencyData)
    path = tmp_path / "quantum_efficiency.nc"
    artifact.save_netcdf(path)
    loaded = QuantumEfficiencyData.load_netcdf(path)
    assert loaded.target == "Q00"
    assert loaded.quantum_efficiency == pytest.approx(0.42)
    np.testing.assert_allclose(loaded.readout_amplitudes, [0.01, 0.02])
    np.testing.assert_allclose(loaded.snr_values, [0.02, 0.04])
    np.testing.assert_allclose(loaded.rho01, [0.48, 0.46])
    np.testing.assert_allclose(
        cast("Any", loaded.projection_weights),
        np.asarray([1.0 + 0.5j, 0.2 - 0.1j]),
    )
    assert loaded.snr_uncertainty_methods == ("fit_covariance", "delta_fallback")


def test_task_dependencies_defaults_registration_and_metric() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401

    assert set(CheckQuantumEfficiency.run_spec) == {
        "readout_duration",
        "amplitude_range",
        "shots",
        "interval",
    }
    assert CheckQuantumEfficiency.run_spec["amplitude_range"].default is None
    assert {"hpi_amplitude", "hpi_duration"} <= set(CheckQuantumEfficiency.input_spec)
    assert not {
        "average_readout_fidelity",
        "readout_fidelity_0",
        "readout_fidelity_1",
    } & set(CheckQuantumEfficiency.input_spec)
    assert BaseTask.registry["qubex"]["CheckQuantumEfficiency"] is CheckQuantumEfficiency
    metric = load_metrics_config().qubit_metrics["quantum_efficiency"]
    assert metric.unit == "%"
    assert metric.scale == 100
    assert metric.evaluation.mode == "maximize"
