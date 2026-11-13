"""Tests for the Qubex thermal-excitation task."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
import qubex.contrib

from qdash.common.config.metrics import load_metrics_config
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import BaseTask, RunResult
from qdash.workflow.calibtasks.qubex.measurement.check_thermal_excitation import (
    CheckThermalExcitation,
)


def _task() -> CheckThermalExcitation:
    task = CheckThermalExcitation()
    values = {
        "control_frequency": 5.0,
        "control_frequency_ef": 4.7,
        "hpi_amplitude": 0.05,
        "hpi_duration": 32.0,
        "ef_pi_amplitude": 0.31,
        "ef_pi_duration": 32.0,
        "readout_amplitude": 0.03,
        "readout_frequency": 6.1,
    }
    for name, value in values.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    task.run_parameters["shots"].value = 4096
    task.run_parameters["interval"].value = 204800.0
    return task


def _experiment() -> Any:
    exp = MagicMock()
    exp.get_qubit_label.return_value = "Q00"
    exp.ctx.resolve_ge_label.return_value = "Q00_ge"
    exp.ctx.resolve_ef_label.return_value = "Q00-ef"
    exp.ctx.resolve_read_label.return_value = "Q00_read"
    exp.targets = {"Q00_ge": object(), "Q00-ef": object()}
    exp.params.readout_amplitude = {}
    applied: list[dict[str, float]] = []

    @contextmanager
    def modified_frequencies(values: dict[str, float]):
        applied.append(values)
        yield

    exp.modified_frequencies.side_effect = modified_frequencies
    exp.applied_frequencies = applied
    return exp


def test_run_passes_frequencies_shots_and_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    exp = _experiment()
    measure = MagicMock(
        return_value=SimpleNamespace(
            data={"p_ex": 0.04, "signal_amplitude": 0.1, "reference_amplitude": 2.4}
        )
    )
    monkeypatch.setattr(qubex.contrib, "measure_thermal_excitation", measure)
    backend = cast("Any", SimpleNamespace(get_instance=lambda: exp))

    result = task.run(backend, "0")

    assert result.raw_result is measure.return_value
    assert exp.applied_frequencies == [{"Q00_ge": 5.0, "Q00-ef": 4.7, "Q00_read": 6.1}]
    assert exp.params.readout_amplitude["Q00"] == 0.03
    measure.assert_called_once_with(
        exp,
        target="Q00",
        n_shots=4096,
        shot_interval=204800.0,
        plot=False,
    )


def test_run_requires_ef_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    task = _task()
    exp = _experiment()
    exp.targets = {"Q00_ge": object()}
    measure = MagicMock()
    monkeypatch.setattr(qubex.contrib, "measure_thermal_excitation", measure)

    with pytest.raises(ValueError, match="EF-capable configuration_mode"):
        task.run(cast("Any", SimpleNamespace(get_instance=lambda: exp)), "0")

    measure.assert_not_called()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("shots", 0, "shots must be positive"),
        ("interval", 0.0, "interval must be finite and positive"),
        ("interval", float("nan"), "interval must be finite and positive"),
    ],
)
def test_run_rejects_invalid_measurement_options(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: float,
    message: str,
) -> None:
    task = _task()
    task.run_parameters[name].value = value
    measure = MagicMock()
    monkeypatch.setattr(qubex.contrib, "measure_thermal_excitation", measure)

    with pytest.raises(ValueError, match=message):
        task.run(cast("Any", SimpleNamespace(get_instance=MagicMock())), "0")

    measure.assert_not_called()


def test_postprocess_publishes_only_valid_probability() -> None:
    task = _task()
    run_result = RunResult(
        raw_result=SimpleNamespace(
            data={"p_ex": 0.04, "signal_amplitude": 0.1, "reference_amplitude": 2.4}
        )
    )

    result = task.postprocess(cast("Any", object()), "exec", run_result, "0")

    assert set(result.output_parameters) == {"thermal_excitation_probability"}
    assert result.output_parameters["thermal_excitation_probability"].value == 0.04
    assert all(parameter.execution_id == "exec" for parameter in result.output_parameters.values())
    assert result.validation_error is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            {"p_ex": 1.1, "signal_amplitude": 0.1, "reference_amplitude": 2.4},
            "thermal excitation probability",
        ),
        (
            {"p_ex": 0.0, "signal_amplitude": float("nan"), "reference_amplitude": 2.4},
            "thermal signal amplitude",
        ),
        (
            {"p_ex": 0.0, "signal_amplitude": 0.1, "reference_amplitude": float("inf")},
            "thermal reference amplitude",
        ),
    ],
)
def test_postprocess_rejects_invalid_results(data: dict[str, float], message: str) -> None:
    result = _task().postprocess(
        cast("Any", object()),
        "exec",
        RunResult(raw_result=SimpleNamespace(data=data)),
        "0",
    )

    assert result.validation_error is not None
    assert message in result.validation_error


def test_task_uses_ge_hpi_and_ef_pi_without_classifier_dependency() -> None:
    ef_frequency = CheckThermalExcitation.input_spec["control_frequency_ef"]
    assert ef_frequency.fallback_parameter_names == ("ef_frequency",)
    assert {"hpi_amplitude", "hpi_duration", "ef_pi_amplitude", "ef_pi_duration"} <= set(
        CheckThermalExcitation.input_spec
    )
    assert not {
        "ef_hpi_amplitude",
        "ef_hpi_duration",
        "average_ef_readout_fidelity",
    } & set(CheckThermalExcitation.input_spec)


def test_qubex_package_registers_thermal_excitation_task() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401

    assert BaseTask.registry["qubex"]["CheckThermalExcitation"] is CheckThermalExcitation


def test_thermal_excitation_probability_is_registered_as_metric() -> None:
    metric = load_metrics_config().qubit_metrics["thermal_excitation_probability"]

    assert metric.unit == "%"
    assert metric.scale == 100
    assert metric.evaluation.mode == "minimize"
