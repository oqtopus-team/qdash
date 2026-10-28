"""Tests for the Qubex readout MIST task."""

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
from qubex.contrib.experiment.readout_mist import (
    GefPopulationSeries,
    ReadoutMistConditionMeasurements,
    ReadoutMistMeasurements,
    analyze_readout_mist,
)

from qdash.common.config.backend import is_task_available
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qubex.measurement.check_readout_mist import (
    CheckReadoutMIST,
    ReadoutMISTData,
    _ReadoutMISTRunPayload,
)


@dataclass(frozen=True)
class _Series:
    population: np.ndarray
    covariance: np.ndarray
    standard_error: np.ndarray
    population_unconstrained: np.ndarray


@dataclass(frozen=True)
class _Condition:
    actual: _Series
    reference: _Series | None


@dataclass(frozen=True)
class _Measurements:
    repetition_counts: np.ndarray
    protocols: dict[str, _Condition]


@dataclass(frozen=True)
class _Fit:
    success: bool
    transition_matrix: np.ndarray
    message: str


@dataclass(frozen=True)
class _Analysis:
    actual: _Fit
    reference: _Fit | None
    reference_difference: dict[str, float] | None


def _task() -> CheckReadoutMIST:
    task = CheckReadoutMIST()
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
    task.run_parameters["shots"].value = 2048
    task.run_parameters["calibration_shots"].value = 4096
    task.run_parameters["interval"].value = 180_000.0
    return task


def _experiment() -> Any:
    exp = MagicMock()
    exp.params.readout_amplitude = {"Q00": 0.01}
    exp.targets = {"Q00": object(), "Q00_ef": object()}
    exp.ctx.resolve_ge_label.return_value = "Q00"
    exp.ctx.resolve_ef_label.return_value = "Q00_ef"
    exp.ctx.resolve_read_label.return_value = "RQ00"
    applied: list[dict[str, float]] = []

    @contextmanager
    def modified_frequencies(values: dict[str, float]):
        applied.append(values)
        yield

    exp.modified_frequencies.side_effect = modified_frequencies
    exp.applied_frequencies = applied
    return exp


def _result(*, actual_success: bool = True, reference_success: bool = True) -> SimpleNamespace:
    counts = np.array([0, 1, 2, 4, 8])
    population = np.tile(np.array([0.98, 0.015, 0.005]), (counts.size, 1))
    series = _Series(
        population=population,
        covariance=np.tile(np.eye(3)[None, :, :] * 1e-4, (counts.size, 1, 1)),
        standard_error=np.full_like(population, 0.01),
        population_unconstrained=population.copy(),
    )
    measurements = _Measurements(
        repetition_counts=counts,
        protocols={
            protocol: _Condition(actual=series, reference=series)
            for protocol in ("initial_g", "initial_e", "initial_f")
        },
    )
    actual = _Fit(actual_success, np.eye(3), "actual status")
    reference = _Fit(reference_success, np.eye(3), "reference status")
    populations = go.Figure()
    transition_matrix = go.Figure()
    return SimpleNamespace(
        data={
            "measurements": measurements,
            "analysis": _Analysis(
                actual=actual,
                reference=reference,
                reference_difference={"g_to_e": 0.001},
            ),
            "raw_data": {"actual_raw_iq": {"point": np.array([1.0 + 2.0j])}},
            "measurement_options": {
                "repetition_counts": counts,
                "measure_reference": True,
            },
            "analysis_options": {"model": "full_six_transition_discrete_time_matrix"},
            "readout_cycle_timing": {"duration_ns": 2048.0, "cycle_gap_ns": 0.0},
            "schedules": {"actual": object(), "reference": object()},
        },
        figure=populations,
        figures={
            "populations": populations,
            "transition_matrix": transition_matrix,
        },
    )


def _run_result(result: Any | None = None) -> RunResult:
    return RunResult(
        raw_result=_ReadoutMISTRunPayload(
            result=_result() if result is None else result,
            target="Q00",
        )
    )


def _qubex_processed_result() -> SimpleNamespace:
    """Build a result with the complete Qubex processed dataclass hierarchy."""
    counts = np.array([0, 1, 2, 4, 8], dtype=np.int64)
    transition = np.array([[0.984, 0.012, 0.007], [0.010, 0.978, 0.023], [0.006, 0.010, 0.970]])
    initial = {
        "initial_g": np.array([0.985, 0.012, 0.003]),
        "initial_e": np.array([0.018, 0.971, 0.011]),
        "initial_f": np.array([0.012, 0.026, 0.962]),
    }
    tangent_covariance = 2e-8 * np.array([[2.0, -1.0, -1.0], [-1.0, 2.0, -1.0], [-1.0, -1.0, 2.0]])
    protocols = {}
    for protocol, population_0 in initial.items():
        population = np.asarray(
            [np.linalg.matrix_power(transition, int(count)) @ population_0 for count in counts]
        )
        covariance = np.repeat(tangent_covariance[None, :, :], counts.size, axis=0)
        protocols[protocol] = ReadoutMistConditionMeasurements(
            actual=GefPopulationSeries(
                population=population,
                covariance=covariance,
                standard_error=np.sqrt(np.diagonal(covariance, axis1=1, axis2=2)),
                population_unconstrained=population.copy(),
            ),
            reference=None,
        )
    measurements = ReadoutMistMeasurements(counts, protocols)
    return SimpleNamespace(
        data={
            "measurements": measurements,
            "analysis": analyze_readout_mist(measurements),
            "measurement_options": {
                "repetition_counts": counts,
                "measure_reference": False,
            },
            "analysis_options": {"model": "full_six_transition_discrete_time_matrix"},
            "readout_cycle_timing": {"duration_ns": 2048.0, "cycle_gap_ns": 0.0},
        },
        figure=None,
        figures={},
    )


def test_qubex_api_provides_the_defaults_used_by_the_task() -> None:
    """Keep the locked Qubex revision aligned with this thin wrapper."""
    parameters = inspect.signature(qubex.contrib.characterize_readout_mist).parameters

    assert parameters["cycle_gap_ns"].default == 0.0
    assert parameters["measure_reference"].default is True
    assert parameters["gef_measurement_n_shots"].default == 4096
    assert parameters["gef_calibration_n_shots"].default == 8192
    assert parameters["enable_tqdm"].default is True


def test_run_passes_only_exposed_options(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    task.run_parameters["cycle_gap"].value = 320.0
    task.run_parameters["measure_reference"].value = False
    exp = _experiment()
    measure = MagicMock(return_value=_result())
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(qubex.contrib, "characterize_readout_mist", measure)

    run_result = task.run(cast("Any", object()), "0")

    assert isinstance(run_result.raw_result, _ReadoutMISTRunPayload)
    assert run_result.raw_result.result is measure.return_value
    assert run_result.raw_result.target == "Q00"
    assert exp.params.readout_amplitude["Q00"] == 0.2
    assert exp.applied_frequencies == [{"Q00": 5.0, "Q00_ef": 4.7, "RQ00": 6.1}]
    kwargs = measure.call_args.kwargs
    assert kwargs["target"] == "Q00"
    assert kwargs["cycle_gap_ns"] == 320.0
    assert kwargs["measure_reference"] is False
    assert kwargs["gef_measurement_n_shots"] == 2048
    assert kwargs["gef_calibration_n_shots"] == 4096
    assert kwargs["shot_interval"] == 180_000.0
    assert kwargs["plot"] is False
    assert not {
        "repetition_counts",
        "acquisition_order",
        "acquisition_seed",
        "enable_tqdm",
    } & set(kwargs)


def test_prepare_run_restores_ge_and_ef_pi_pulses() -> None:
    """MIST should use the standard QDash pulse-context restoration path."""
    task = _task()
    exp = _experiment()
    exp.get_qubit_label.return_value = "Q00"
    backend = MagicMock()
    backend.get_instance.return_value = exp

    task.prepare_run(cast("Any", backend), "0")

    assert exp.calib_note.update_pi_param.call_count == 2
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
        ("cycle_gap", -1.0, "finite and nonnegative"),
        ("measure_reference", 1, "must be boolean"),
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


def test_extract_raw_data_round_trips_only_processed_results(tmp_path: Any) -> None:
    artifact = _task().extract_raw_data(_run_result())[0]

    assert isinstance(artifact, ReadoutMISTData)
    assert not hasattr(artifact, "raw_data")
    assert not hasattr(artifact, "schedules")
    path = tmp_path / "readout_mist.nc"
    artifact.save_netcdf(path)
    loaded = ReadoutMISTData.load_netcdf(path)
    assert loaded.target == "Q00"
    np.testing.assert_array_equal(loaded.repetition_counts, [0, 1, 2, 4, 8])
    np.testing.assert_allclose(
        loaded.measurements["protocols"]["initial_g"]["actual"]["population"][0],
        [0.98, 0.015, 0.005],
    )
    np.testing.assert_allclose(loaded.analysis["actual"]["transition_matrix"], np.eye(3))
    assert loaded.measurement_options["measure_reference"] is True


def test_artifact_round_trips_complete_qubex_processed_records(tmp_path: Any) -> None:
    """The real nested Qubex fit records should remain NetCDF-compatible."""
    artifact = _task().extract_raw_data(_run_result(_qubex_processed_result()))[0]

    path = tmp_path / "readout_mist_complete.nc"
    artifact.save_netcdf(path)
    loaded = ReadoutMISTData.load_netcdf(path)

    assert loaded.analysis["actual"]["success"] is True
    assert loaded.analysis["reference"] is None
    assert loaded.analysis["actual"]["state_order"] == ["g", "e", "f"]
    assert loaded.analysis["actual"]["goodness_of_fit"]["degrees_of_freedom"] > 0
    assert loaded.measurements["protocols"]["initial_f"]["reference"] is None


def test_postprocess_keeps_both_figures() -> None:
    result = _result()

    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        _run_result(result),
        "0",
    )

    assert processed.output_parameters == {}
    assert processed.figures == [
        result.figures["populations"],
        result.figures["transition_matrix"],
    ]
    assert processed.validation_error is None


def test_postprocess_accepts_a_successful_measurement_without_reference() -> None:
    """Disabling the optional blank reference should not make the task fail."""
    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        _run_result(_qubex_processed_result()),
        "0",
    )

    assert processed.validation_error is None
    assert processed.figures == []


@pytest.mark.parametrize(
    ("actual_success", "reference_success", "message"),
    [
        (False, True, "actual fit failed"),
        (True, False, "reference fit failed"),
    ],
)
def test_postprocess_rejects_failed_requested_fits(
    actual_success: bool, reference_success: bool, message: str
) -> None:
    processed = _task().postprocess(
        cast("Any", object()),
        "exec",
        _run_result(
            _result(
                actual_success=actual_success,
                reference_success=reference_success,
            )
        ),
        "0",
    )

    assert processed.validation_error is not None
    assert message in processed.validation_error


def test_task_dependencies_defaults_and_registration() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401

    assert set(CheckReadoutMIST.run_spec) == {
        "cycle_gap",
        "measure_reference",
        "shots",
        "calibration_shots",
        "interval",
    }
    assert CheckReadoutMIST.run_spec["measure_reference"].default is True
    assert {
        "control_frequency",
        "control_frequency_ef",
        "readout_frequency",
        "readout_amplitude",
        "pi_amplitude",
        "pi_duration",
        "ef_pi_amplitude",
        "ef_pi_duration",
    } == set(CheckReadoutMIST.input_spec)
    assert CheckReadoutMIST.output_spec == {}
    assert CheckReadoutMIST().get_progress_plan().minimum_phases == 2
    assert CheckReadoutMIST().get_progress_plan().maximum_phases == 2
    assert BaseTask.registry["qubex"]["CheckReadoutMIST"] is CheckReadoutMIST
    assert is_task_available("CheckReadoutMIST", "qubex")
