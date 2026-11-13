"""Tests for the Qubex CPMG noise spectroscopy task."""

import inspect
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
import qubex.contrib

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qubex.measurement.check_cpmg_noise_spectroscopy import (
    CheckCPMGNoiseSpectroscopy,
    CPMGNoiseSpectroscopyData,
)


def _task() -> CheckCPMGNoiseSpectroscopy:
    task = CheckCPMGNoiseSpectroscopy()
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
        "pi_amplitude": 0.1,
        "pi_duration": 48.0,
        "drag_pi_amplitude": 0.09,
        "drag_pi_duration": 40.0,
        "drag_pi_beta": -0.4,
    }
    for name, value in values.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    task.run_parameters["frequency_range"].value = [0.001, 0.002]
    task.run_parameters["frequency_range"].value_type = "list"
    task.run_parameters["time_range"].value = [8_000.0, 12_000.0, 20_000.0]
    task.run_parameters["time_range"].value_type = "list"
    task.run_parameters["shots"].value = 2048
    task.run_parameters["interval"].value = 180_000.0
    task.run_parameters["pi_pulse_pattern"].value = "+--+"
    return task


def _experiment() -> tuple[Any, MagicMock, MagicMock]:
    pi_pulse = MagicMock(name="pi_pulse")
    drag_pi_pulse = MagicMock(name="drag_pi_pulse")
    pi_pulse.shifted.return_value = MagicMock(name="y_pi_pulse")
    drag_pi_pulse.shifted.return_value = MagicMock(name="y_drag_pi_pulse")
    exp = MagicMock()
    exp.params.readout_amplitude = {"Q00": 0.01}
    exp.pi_pulse = {"Q00": pi_pulse}
    exp.drag_pi_pulse = {"Q00": drag_pi_pulse}
    applied: list[dict[str, float]] = []

    @contextmanager
    def modified_frequencies(values: dict[str, float]):
        applied.append(values)
        yield

    exp.modified_frequencies.side_effect = modified_frequencies
    exp.applied_frequencies = applied
    return exp, pi_pulse, drag_pi_pulse


def _result(*, all_fits_failed: bool = False) -> Any:
    summary = go.Figure()
    heatmap = go.Figure()
    gamma2 = np.full((1, 1, 2), np.nan)
    if not all_fits_failed:
        gamma2[0, 0, 0] = 1.0 / 40_000.0
    t2 = np.full_like(gamma2, np.nan)
    finite = np.isfinite(gamma2) & (gamma2 > 0)
    t2[finite] = 1.0 / gamma2[finite]
    fit_records = (
        {
            "target": "Q00",
            "repeat_index": 0,
            "requested_frequency_index": 0,
            "fit_status": "optimizer_failed" if all_fits_failed else "ok",
            "quality_flags": [],
            "n_pi_values": [16, 24, 40],
            "actual_decay_times_ns": [8_000.0, 12_000.0, 20_000.0],
            "P_values": [0.84, 0.76, 0.63],
        },
    )
    return SimpleNamespace(
        data={
            "schema_version": 2,
            "timestamp": "20261026_120000",
            "targets": ["Q00"],
            "n_repeats": 1,
            "frequency_range": [0.001, 0.002],
            "realized_frequency_matrix": np.array([[0.001, 0.002]]),
            "valid_frequency_mask": np.array([[True, True]]),
            "half_tau_range": [240.0, 115.0],
            "time_range": [8_000.0, 12_000.0, 20_000.0],
            "t2_matrix": t2,
            "t2_error_matrix": np.full_like(t2, 500.0),
            "gamma2_matrix": gamma2,
            "gamma2_error_matrix": np.full_like(gamma2, 1e-6),
            "r2_matrix": np.where(finite, 0.98, np.nan),
            "fit_records": list(fit_records),
            "frequency_plans": [
                [
                    {"requested_index": 0, "status": "valid"},
                    {"requested_index": 1, "status": "valid"},
                ]
            ],
            "acquisition_orders": [[[1, 0]]],
            "random_seed": 1234,
            "random_seed_requested": None,
            "metadata": {
                "pi_pulse_pattern": "+--+",
                "frequency_definition": "1 / (2 * pi_center_spacing)",
            },
            "failed_fits": (
                [{"target": "Q00", "status": "optimizer_failed"}] if all_fits_failed else []
            ),
        },
        figure=summary,
        figures={"summary": summary, "Q00_raw_data_heatmap": heatmap},
    )


def test_qubex_api_retains_options_delegated_by_task() -> None:
    """Options not exposed by QDash should remain optional in the locked Qubex API."""
    parameters = inspect.signature(qubex.contrib.cpmg_noise_spectroscopy).parameters

    for name in (
        "n_repeats",
        "save_fit_images",
        "summary_mode",
        "xaxis_type",
        "enable_tqdm",
    ):
        assert parameters[name].default is None


def test_run_prefers_drag_pi_and_passes_only_selected_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stored DRAG PI should be phase shifted and passed to the Qubex workflow."""
    task = _task()
    exp, pi_pulse, drag_pi_pulse = _experiment()
    measure = MagicMock(return_value=_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "get_resonator_label", lambda _backend, _qid: "RQ00")
    monkeypatch.setattr(qubex.contrib, "cpmg_noise_spectroscopy", measure)

    run_result = task.run(cast("Any", object()), "0")

    assert run_result.raw_result is measure.return_value
    assert exp.params.readout_amplitude["Q00"] == 0.2
    assert exp.applied_frequencies == [{"Q00": 5.0, "RQ00": 6.1}]
    drag_pi_pulse.shifted.assert_called_once_with(np.pi / 2)
    pi_pulse.shifted.assert_not_called()
    kwargs = measure.call_args.kwargs
    assert kwargs["targets"] == ["Q00"]
    np.testing.assert_allclose(kwargs["frequency_range"], [0.001, 0.002])
    np.testing.assert_allclose(kwargs["time_range"], [8_000.0, 12_000.0, 20_000.0])
    assert kwargs["pi_pulses"] == {"Q00": drag_pi_pulse.shifted.return_value}
    assert kwargs["pi_pulse_pattern"] == "+--+"
    assert kwargs["n_shots"] == 2048
    assert kwargs["shot_interval"] == 180_000.0
    assert kwargs["plot"] is False
    assert kwargs["save_image"] is False
    assert kwargs["save_data"] is False
    assert not {
        "readout_duration",
        "n_repeats",
        "min_pi_pulses",
        "max_pulse_duty_ratio",
        "min_fit_points",
        "frequency_order",
        "random_seed",
        "save_fit_images",
        "summary_mode",
        "show_t1",
        "xaxis_type",
        "enable_tqdm",
    } & set(kwargs)


@pytest.mark.parametrize(
    ("drag_amplitude", "drag_duration", "drag_beta"),
    [
        (0.0, 0.0, 0.0),
        (0.09, 0.0, -0.4),
        (0.0, 40.0, -0.4),
        (0.09, 40.0, float("inf")),
    ],
)
def test_run_falls_back_to_plain_pi_when_drag_is_unavailable_or_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    drag_amplitude: float,
    drag_duration: float,
    drag_beta: float,
) -> None:
    """Missing or incomplete DRAG calibration should select the non-DRAG PI pulse."""
    task = _task()
    task.input_parameters["drag_pi_amplitude"].value = drag_amplitude
    task.input_parameters["drag_pi_duration"].value = drag_duration
    task.input_parameters["drag_pi_beta"].value = drag_beta
    exp, pi_pulse, drag_pi_pulse = _experiment()
    measure = MagicMock(return_value=_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "get_resonator_label", lambda _backend, _qid: "RQ00")
    monkeypatch.setattr(qubex.contrib, "cpmg_noise_spectroscopy", measure)

    task.run(cast("Any", object()), "0")

    pi_pulse.shifted.assert_called_once_with(np.pi / 2)
    drag_pi_pulse.shifted.assert_not_called()
    assert measure.call_args.kwargs["pi_pulses"] == {"Q00": pi_pulse.shifted.return_value}


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("frequency_range", [], "frequency_range must be a non-empty 1D array"),
        ("time_range", [100.0, float("nan")], "time_range must contain positive"),
        ("shots", 0, "shots must be positive"),
        ("interval", float("inf"), "interval must be finite and positive"),
        ("pi_pulse_pattern", "invalid", "pi_pulse_pattern must be one of"),
    ],
)
def test_run_rejects_invalid_options(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: Any,
    message: str,
) -> None:
    """Invalid task options should fail before invoking the Qubex experiment."""
    task = _task()
    task.run_parameters[name].value = value
    measure = MagicMock()
    monkeypatch.setattr(qubex.contrib, "cpmg_noise_spectroscopy", measure)

    with pytest.raises(ValueError, match=message):
        task.run(cast("Any", SimpleNamespace(get_instance=MagicMock())), "0")

    measure.assert_not_called()


def test_postprocess_returns_summary_and_heatmap_when_one_fit_succeeds() -> None:
    """One finite fit should make the task successful and retain both result figures."""
    raw_result = _result()

    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        RunResult(raw_result=raw_result),
        "0",
    )

    assert processed.output_parameters == {}
    assert processed.figures == [
        raw_result.figures["summary"],
        raw_result.figures["Q00_raw_data_heatmap"],
    ]
    assert processed.validation_error is None


def test_postprocess_fails_when_every_fit_fails_but_keeps_figures() -> None:
    """All failed fits should fail the task without discarding diagnostic figures."""
    raw_result = _result(all_fits_failed=True)

    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        RunResult(raw_result=raw_result),
        "0",
    )

    assert len(processed.figures) == 2
    assert processed.validation_error == "CPMG fit failed at all frequencies for Q00."


def test_extract_raw_data_round_trips_reanalysis_payload(tmp_path: Any) -> None:
    """The NetCDF artifact should retain matrices, measured curves, and fit diagnostics."""
    artifact = _task().extract_raw_data(RunResult(raw_result=_result()))[0]

    assert isinstance(artifact, CPMGNoiseSpectroscopyData)
    path = tmp_path / "cpmg_noise_spectroscopy.nc"
    artifact.save_netcdf(path)
    loaded = CPMGNoiseSpectroscopyData.load_netcdf(path)
    assert loaded.target == "Q00"
    np.testing.assert_allclose(loaded.realized_frequency_range, [0.001, 0.002])
    np.testing.assert_allclose(loaded.t2_matrix[0, 0], 40_000.0)
    assert loaded.fit_records[0]["n_pi_values"] == [16, 24, 40]
    assert loaded.frequency_plan[0]["status"] == "valid"
    assert loaded.metadata["pi_pulse_pattern"] == "+--+"


def test_extract_raw_data_preserves_every_repeat(tmp_path: Any) -> None:
    """Selecting the sole target must not discard the repeat axis."""
    raw_result = _result()
    data = raw_result.data
    t2 = np.array([[[40_000.0, np.nan], [50_000.0, 60_000.0]]])
    gamma2 = 1.0 / t2
    data.update(
        {
            "n_repeats": 2,
            "t2_matrix": t2,
            "t2_error_matrix": np.full_like(t2, 500.0),
            "gamma2_matrix": gamma2,
            "gamma2_error_matrix": np.full_like(gamma2, 1e-6),
            "r2_matrix": np.array([[[0.98, np.nan], [0.97, 0.96]]]),
            "acquisition_orders": [[[1, 0], [0, 1]]],
        }
    )
    data["fit_records"].append(
        {
            "target": "Q00",
            "repeat_index": 1,
            "requested_frequency_index": 0,
            "fit_status": "ok",
            "quality_flags": [],
            "n_pi_values": [16, 24, 40],
            "actual_decay_times_ns": [8_000.0, 12_000.0, 20_000.0],
            "P_values": [0.82, 0.72, 0.58],
        }
    )

    artifact = _task().extract_raw_data(RunResult(raw_result=raw_result))[0]
    path = tmp_path / "cpmg_noise_spectroscopy_repeats.nc"
    artifact.save_netcdf(path)
    loaded = CPMGNoiseSpectroscopyData.load_netcdf(path)

    assert loaded.n_repeats == 2
    assert loaded.t2_matrix.shape == (2, 2)
    np.testing.assert_allclose(loaded.t2_matrix[1], [50_000.0, 60_000.0])
    np.testing.assert_allclose(loaded.gamma2_matrix[1], 1.0 / np.array([50_000.0, 60_000.0]))
    np.testing.assert_array_equal(loaded.acquisition_orders, [[1, 0], [0, 1]])
    assert loaded.fit_records[-1]["repeat_index"] == 1


def test_task_defaults_dependencies_and_registration() -> None:
    """The task should expose only agreed run options and optional DRAG inputs."""
    import qdash.workflow.calibtasks.qubex  # noqa: F401

    assert set(CheckCPMGNoiseSpectroscopy.run_spec) == {
        "frequency_range",
        "time_range",
        "shots",
        "interval",
        "pi_pulse_pattern",
    }
    frequency_spec = CheckCPMGNoiseSpectroscopy.run_spec["frequency_range"]
    assert frequency_spec.value_type == "np.linspace"
    assert frequency_spec.default == (0.0005, 0.004, 20)
    time_spec = CheckCPMGNoiseSpectroscopy.run_spec["time_range"]
    assert time_spec.value_type == "np.logspace"
    np.testing.assert_allclose(
        time_spec.create_model().get_value(),
        np.geomspace(200.0, 200_000.0, 31),
    )
    assert "readout_duration" not in CheckCPMGNoiseSpectroscopy.run_spec
    assert {"hpi_amplitude", "hpi_duration", "pi_amplitude", "pi_duration"} <= set(
        CheckCPMGNoiseSpectroscopy.input_spec
    )
    for name in ("drag_pi_amplitude", "drag_pi_duration", "drag_pi_beta"):
        assert CheckCPMGNoiseSpectroscopy.input_spec[name].resolution == "database_or_default"
        assert CheckCPMGNoiseSpectroscopy.input_spec[name].default == 0
    assert BaseTask.registry["qubex"]["CheckCPMGNoiseSpectroscopy"] is CheckCPMGNoiseSpectroscopy
