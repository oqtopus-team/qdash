"""Tests for the Qubex GEF relaxation task."""

import inspect
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import plotly.graph_objects as go
import pytest
import qubex.contrib

from qdash.common.config.backend import is_task_available
from qdash.common.config.metrics import load_metrics_config
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qubex.measurement.check_gef_relaxation import (
    CheckGEFRelaxation,
    GEFRelaxationData,
    _GEFRelaxationRunPayload,
)


@dataclass(frozen=True)
class _Estimate:
    value: float
    standard_error: float | None
    estimable: bool = True


@dataclass(frozen=True)
class _Fit:
    success: bool
    derived_times_ns: dict[str, _Estimate]
    message: str = "fit status"


@dataclass(frozen=True)
class _Measurements:
    time_ns: np.ndarray
    protocols: dict[str, Any]


def _task() -> CheckGEFRelaxation:
    task = CheckGEFRelaxation()
    values = {
        "control_frequency": 5.0,
        "control_frequency_ef": 4.7,
        "readout_frequency": 6.1,
        "readout_amplitude": 0.2,
        "pi_amplitude": 0.1,
        "pi_duration": 48.0,
        "ef_pi_amplitude": 0.12,
        "ef_pi_duration": 52.0,
    }
    for name, value in values.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    task.run_parameters["time_range"].value_type = "list"
    task.run_parameters["time_range"].value = [100.0, 1_000.0, 10_000.0, 100_000.0]
    task.run_parameters["shots"].value = 2048
    task.run_parameters["calibration_shots"].value = 4096
    task.run_parameters["interval"].value = 180_000.0
    return task


def _experiment() -> Any:
    exp = MagicMock()
    exp.get_qubit_label.return_value = "Q00"
    exp.params.readout_amplitude = {"Q00": 0.01}
    exp.targets = {"Q00_ge": object(), "Q00_ef": object()}
    exp.ctx.resolve_ge_label.return_value = "Q00_ge"
    exp.ctx.resolve_ef_label.return_value = "Q00_ef"
    exp.ctx.resolve_read_label.return_value = "Q00_read"
    applied: list[dict[str, float]] = []

    @contextmanager
    def modified_frequencies(values: dict[str, float]):
        applied.append(values)
        yield

    exp.modified_frequencies.side_effect = modified_frequencies
    exp.applied_frequencies = applied
    return exp


def _result(
    *, success: bool = True, non_estimable: str | None = None, invalid: str | None = None
) -> SimpleNamespace:
    estimates = {
        "t1_e_to_g": _Estimate(100_000.0, 2_000.0),
        "t1_f_to_e": _Estimate(60_000.0, 1_500.0),
        "t1_f_to_g": _Estimate(240_000.0, 5_000.0),
    }
    if non_estimable is not None:
        estimate = estimates[non_estimable]
        estimates[non_estimable] = _Estimate(
            estimate.value, estimate.standard_error, estimable=False
        )
    if invalid is not None:
        estimate = estimates[invalid]
        estimates[invalid] = _Estimate(float("nan"), estimate.standard_error)
    populations = go.Figure()
    rates = go.Figure()
    time_ns = np.array([0.0, 100.0, 1_000.0, 10_000.0, 100_000.0])
    return SimpleNamespace(
        data={
            "measurements": {"Q00": _Measurements(time_ns, {"initial_g": {}})},
            "analysis": {"Q00": _Fit(success, estimates)},
            "raw_data": {"raw_iq": {"point": np.array([1.0 + 2.0j])}},
            "measurement_options": {"time_ns": time_ns, "gef_measurement_n_shots": 2048},
            "analysis_options": {"model": "continuous_time_three_state_markov_generator"},
        },
        figure=populations,
        figures={"Q00/populations": populations, "Q00/rates": rates},
    )


def _run_result(result: Any | None = None) -> RunResult:
    return RunResult(
        raw_result=_GEFRelaxationRunPayload(
            result=_result() if result is None else result,
            target="Q00",
        )
    )


def test_qubex_api_provides_the_defaults_used_by_the_task() -> None:
    """Keep the pinned Qubex revision aligned with this thin wrapper."""
    parameters = inspect.signature(qubex.contrib.characterize_gef_relaxation).parameters

    assert parameters["gef_measurement_n_shots"].default == 4096
    assert parameters["gef_calibration_n_shots"].default == 8192
    assert parameters["covariance_rcond"].default == 1e-12
    assert parameters["acquisition_order"].default == "interleaved"
    assert parameters["acquisition_seed"].default == 0


def test_run_passes_calibrations_and_measurement_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _task()
    exp = _experiment()
    measure = MagicMock(return_value=_result())
    monkeypatch.setattr(qubex.contrib, "characterize_gef_relaxation", measure, raising=False)
    backend = cast("Any", SimpleNamespace(get_instance=lambda: exp))

    run_result = task.run(backend, "0")

    assert isinstance(run_result.raw_result, _GEFRelaxationRunPayload)
    assert run_result.raw_result.target == "Q00"
    assert exp.params.readout_amplitude["Q00"] == 0.2
    assert exp.applied_frequencies == [{"Q00_ge": 5.0, "Q00_ef": 4.7, "Q00_read": 6.1}]
    measure.assert_called_once_with(
        exp,
        targets=["Q00"],
        time_range=[0.0, 100.0, 1_000.0, 10_000.0, 100_000.0],
        gef_measurement_n_shots=2048,
        gef_calibration_n_shots=4096,
        shot_interval=180_000.0,
        plot=False,
    )


def test_prepare_run_restores_ge_and_ef_pi_pulses() -> None:
    task = _task()
    exp = _experiment()
    backend = cast("Any", SimpleNamespace(get_instance=lambda: exp))

    task.prepare_run(backend, "0")

    ge_call, ef_call = exp.calib_note.update_pi_param.call_args_list
    assert ge_call.args[0] == "Q00"
    assert ge_call.args[1]["amplitude"] == 0.1
    assert ge_call.args[1]["duration"] == 48.0
    assert ef_call.args[0] == "Q00_ef"
    assert ef_call.args[1]["amplitude"] == 0.12
    assert ef_call.args[1]["duration"] == 52.0


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("time_range", [0.0, 100.0, 1_000.0, 10_000.0], "strictly positive"),
        ("time_range", [100.0, 1_000.0, 10_000.0], "at least four"),
        ("shots", 1, "shots must be at least two"),
        ("calibration_shots", 1, "calibration_shots must be at least two"),
        ("interval", float("nan"), "interval must be finite and positive"),
    ],
)
def test_run_rejects_invalid_options(name: str, value: Any, message: str) -> None:
    task = _task()
    task.run_parameters[name].value = value

    with pytest.raises((TypeError, ValueError), match=message):
        task._run_kwargs()


def test_postprocess_publishes_directional_times_in_microseconds() -> None:
    result = _result()

    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        _run_result(result),
        "0",
    )

    assert processed.validation_error is None
    assert processed.output_parameters["t1"].value == 100.0
    assert processed.output_parameters["t1"].error == 2.0
    assert processed.output_parameters["t1_fe"].value == 60.0
    assert processed.output_parameters["t1_fe"].error == 1.5
    assert processed.output_parameters["t1_fg"].value == 240.0
    assert processed.output_parameters["t1_fg"].error == 5.0
    assert all(
        parameter.execution_id == "exec" for parameter in processed.output_parameters.values()
    )
    assert processed.figures == [
        result.figures["Q00/populations"],
        result.figures["Q00/rates"],
    ]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (_result(success=False), "fit failed"),
        (_result(non_estimable="t1_e_to_g"), "t1 (Qubex t1_e_to_g) is not estimable"),
        (_result(non_estimable="t1_f_to_e"), "t1_fe (Qubex t1_f_to_e) is not estimable"),
        (_result(non_estimable="t1_f_to_g"), "t1_fg (Qubex t1_f_to_g) is not estimable"),
        (_result(invalid="t1_f_to_e"), "t1_fe (Qubex t1_f_to_e) is non-finite"),
    ],
)
def test_postprocess_rejects_failed_or_unusable_estimates(result: Any, message: str) -> None:
    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        _run_result(result),
        "0",
    )

    assert processed.output_parameters == {}
    assert processed.validation_error is not None
    assert message in processed.validation_error


def test_extract_raw_data_round_trips_processed_results(tmp_path: Any) -> None:
    artifact = _task().extract_raw_data(_run_result())[0]

    assert isinstance(artifact, GEFRelaxationData)
    assert not hasattr(artifact, "raw_data")
    path = tmp_path / "gef_relaxation.nc"
    artifact.save_netcdf(path)
    loaded = GEFRelaxationData.load_netcdf(path)
    assert loaded.target == "Q00"
    np.testing.assert_array_equal(loaded.time_ns, [0.0, 100.0, 1_000.0, 10_000.0, 100_000.0])
    assert loaded.analysis["success"] is True
    assert loaded.analysis["derived_times_ns"]["t1_f_to_e"]["value"] == 60_000.0


def test_task_dependencies_defaults_registration_and_metrics() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401

    assert set(CheckGEFRelaxation.run_spec) == {
        "readout_duration",
        "time_range",
        "shots",
        "calibration_shots",
        "interval",
    }
    assert set(CheckGEFRelaxation.output_spec) == {"t1", "t1_fe", "t1_fg"}
    assert CheckGEFRelaxation.run_spec["time_range"].value_type == "np.logspace"
    np.testing.assert_allclose(
        CheckGEFRelaxation.run_spec["time_range"].create_model().get_value(),
        np.geomspace(200.0, 200e3, 18),
    )
    assert BaseTask.registry["qubex"]["CheckGEFRelaxation"] is CheckGEFRelaxation
    assert is_task_available("CheckGEFRelaxation", "qubex")
    assert CheckGEFRelaxation().get_progress_plan().minimum_phases == 2
    assert CheckGEFRelaxation().get_progress_plan().maximum_phases == 2

    metrics = load_metrics_config()
    assert metrics.qubit_metrics["t1_fe"].unit == "μs"
    assert metrics.qubit_metrics["t1_fg"].unit == "μs"
    coherence = next(group for group in metrics.cdf_groups.qubit if group.id == "coherence")
    assert {"t1_fe", "t1_fg"} <= set(coherence.metrics)
    assert not {"t1_f_to_e", "t1_f_to_g"} & set(metrics.qubit_metrics)
    assert not {"t1_f_to_e", "t1_f_to_g"} & set(coherence.metrics)
