"""EF calibration tasks preserve transition-specific calibration context."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import plotly.graph_objects as go
import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.qubex.measurement.ef_readout_classification import (
    EFReadoutClassification,
)
from qdash.workflow.calibtasks.qubex.one_qubit_fine.check_ef_rabi import CheckEFRabi
from qdash.workflow.calibtasks.qubex.one_qubit_fine.create_ef_hpi_pulse import (
    CreateEFHPIPulse,
)
from qdash.workflow.calibtasks.qubex.one_qubit_fine.create_ef_pi_pulse import CreateEFPIPulse


class _RabiData:
    @staticmethod
    def fit() -> dict[str, Any]:
        return {"fig": go.Figure()}


class _PulseData:
    def __init__(self, *, calib_value: float = 0.21, r2: float = 0.97) -> None:
        self.calib_value = calib_value
        self.r2 = r2

    @staticmethod
    def fit() -> dict[str, Any]:
        return {"fig": go.Figure()}


def _set_inputs(task: Any) -> None:
    values = {
        "control_frequency": 5.0,
        "control_frequency_ef": 4.7,
        "control_amplitude": 0.02,
        "readout_frequency": 6.1,
        "readout_amplitude": 0.03,
        "hpi_amplitude": 0.05,
        "hpi_duration": 32.0,
        "ef_hpi_amplitude": 0.16,
        "ef_hpi_duration": 32.0,
        "ef_rabi_amplitude": 0.4,
        "ef_rabi_frequency": 12.5,
        "ef_rabi_phase": 0.1,
        "ef_rabi_offset": 0.2,
        "ef_rabi_angle": 0.3,
        "ef_rabi_noise": 0.01,
        "ef_rabi_distance": -0.2,
        "ef_rabi_reference_phase": 0.4,
        "ef_rabi_r2": 0.98,
    }
    for name in task.input_parameters:
        if name in values:
            task.input_parameters[name] = InputParameterModel(value=values[name])


def _experiment() -> Any:
    exp = MagicMock()
    exp.get_qubit_label.return_value = "Q00"
    exp.ctx.resolve_ge_label.return_value = "Q00_ge"
    exp.ctx.resolve_ef_label.return_value = "Q00-ef"
    exp.ctx.resolve_read_label.return_value = "Q00_read"
    exp.targets = {"Q00_ge": object(), "Q00-ef": object()}
    exp.params.readout_amplitude = {}
    exp.params.control_amplitude = {}
    exp.classifier_dir = "/tmp/classifiers"
    applied: list[dict[str, float]] = []

    @contextmanager
    def modified_frequencies(values: dict[str, float]):
        applied.append(values)
        yield

    exp.modified_frequencies.side_effect = modified_frequencies
    exp.applied_frequencies = applied
    return exp


def _backend(exp: Any) -> Any:
    return cast("Any", SimpleNamespace(get_instance=lambda: exp))


@pytest.mark.parametrize(
    "task_type",
    [CheckEFRabi, CreateEFHPIPulse, CreateEFPIPulse, EFReadoutClassification],
)
@pytest.mark.parametrize(
    ("frequency_sources", "expected_source"),
    [
        ([{"control_frequency_ef": 4.7}], "control_frequency_ef"),
        ([{"control_frequency_ef": 4.7, "ef_frequency": 4.8}], "control_frequency_ef"),
        ([{"ef_frequency": 4.8}, {"control_frequency_ef": 4.7}], "control_frequency_ef"),
        ([{"ef_frequency": 4.7}], "ef_frequency"),
    ],
)
def test_ef_tasks_resolve_control_frequency_before_measured_frequency(
    task_type: type[CheckEFRabi | CreateEFHPIPulse | CreateEFPIPulse | EFReadoutClassification],
    frequency_sources: list[dict[str, float]],
    expected_source: str,
) -> None:
    task = task_type()
    _set_inputs(task)
    other_inputs = {
        name: parameter.model_dump()
        for name, parameter in task.input_parameters.items()
        if name != "control_frequency_ef"
    }
    sources: list[dict[str, Any]] = [
        {
            name: {
                "value": value,
                "unit": "GHz",
                "execution_id": f"exec-{name}",
                "task_id": f"task-{name}",
            }
            for name, value in source.items()
        }
        for source in frequency_sources
    ]
    sources[0].update(other_inputs)

    task._populate_parameters({"self": sources})

    frequency = task.input_parameters["control_frequency_ef"]
    assert frequency.value == pytest.approx(4.7)
    assert frequency.unit == "GHz"
    assert frequency.parameter_name == expected_source
    assert frequency.execution_id == f"exec-{expected_source}"
    assert frequency.task_id == f"task-{expected_source}"


def test_check_ef_rabi_uses_control_frequency_ef_and_publishes_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = CheckEFRabi()
    _set_inputs(task)
    exp = _experiment()
    rabi_param = SimpleNamespace(
        amplitude=0.4,
        frequency=0.0125,
        phase=0.1,
        offset=0.2,
        angle=0.3,
        noise=0.01,
        distance=-0.2,
        reference_phase=0.4,
        r2=0.98,
    )
    raw = SimpleNamespace(
        rabi_params={"Q00-ef": rabi_param},
        data={"Q00-ef": _RabiData()},
    )
    exp.obtain_ef_rabi_params.return_value = raw
    save_calibration = MagicMock()
    monkeypatch.setattr(task, "save_calibration", save_calibration)

    run_result = task.run(_backend(exp), "0")
    processed = task.postprocess(_backend(exp), "exec", run_result, "0")

    assert exp.applied_frequencies == [{"Q00_ge": 5.0, "Q00-ef": 4.7, "Q00_read": 6.1}]
    assert exp.obtain_ef_rabi_params.call_args.kwargs["targets"] == "Q00"
    assert exp.obtain_ef_rabi_params.call_args.kwargs["plot"] is False
    assert processed.output_parameters["ef_rabi_frequency"].value == pytest.approx(12.5)
    assert processed.output_parameters["ef_rabi_r2"].value == pytest.approx(0.98)
    assert processed.validation_error is None
    save_calibration.assert_called_once()


def test_check_ef_rabi_requires_ge_hpi_instead_of_drag_pi() -> None:
    assert "hpi_amplitude" in CheckEFRabi.input_spec
    assert "hpi_duration" in CheckEFRabi.input_spec
    assert "drag_pi_amplitude" not in CheckEFRabi.input_spec
    assert "drag_pi_duration" not in CheckEFRabi.input_spec
    assert "drag_pi_beta" not in CheckEFRabi.input_spec


@pytest.mark.parametrize(
    ("task_type", "method_name", "duration_name", "output_name"),
    [
        (CreateEFHPIPulse, "calibrate_ef_hpi_pulse", "ef_hpi_duration", "ef_hpi_amplitude"),
        (CreateEFPIPulse, "calibrate_ef_pi_pulse", "ef_pi_duration", "ef_pi_amplitude"),
    ],
)
def test_create_ef_pulse_tasks_publish_transition_specific_parameters(
    monkeypatch: pytest.MonkeyPatch,
    task_type: type[CreateEFHPIPulse | CreateEFPIPulse],
    method_name: str,
    duration_name: str,
    output_name: str,
) -> None:
    task = task_type()
    _set_inputs(task)
    exp = _experiment()
    getattr(exp, method_name).return_value = SimpleNamespace(data={"Q00-ef": _PulseData()})
    save_calibration = MagicMock()
    monkeypatch.setattr(task, "save_calibration", save_calibration)

    run_result = task.run(_backend(exp), "0")
    processed = task.postprocess(_backend(exp), "exec", run_result, "0")

    kwargs = getattr(exp, method_name).call_args.kwargs
    assert exp.applied_frequencies == [{"Q00_ge": 5.0, "Q00-ef": 4.7, "Q00_read": 6.1}]
    assert kwargs["targets"] == "Q00"
    assert kwargs["plot"] is False
    assert processed.output_parameters[output_name].value == pytest.approx(0.21)
    assert (
        processed.output_parameters[duration_name].value
        == task.run_parameters[duration_name].get_value()
    )
    assert processed.validation_error is None
    save_calibration.assert_called_once()


@pytest.mark.parametrize(
    ("task_type", "method_name"),
    [
        (CreateEFHPIPulse, "calibrate_ef_hpi_pulse"),
        (CreateEFPIPulse, "calibrate_ef_pi_pulse"),
    ],
)
def test_create_ef_pulse_tasks_do_not_save_non_finite_fit(
    monkeypatch: pytest.MonkeyPatch,
    task_type: type[CreateEFHPIPulse | CreateEFPIPulse],
    method_name: str,
) -> None:
    task = task_type()
    _set_inputs(task)
    exp = _experiment()
    getattr(exp, method_name).return_value = SimpleNamespace(
        data={"Q00-ef": _PulseData(r2=float("nan"))}
    )
    save_calibration = MagicMock()
    monkeypatch.setattr(task, "save_calibration", save_calibration)

    run_result = task.run(_backend(exp), "0")
    processed = task.postprocess(_backend(exp), "exec", run_result, "0")

    assert run_result.r2 == {"0": None}
    assert processed.validation_error is not None
    save_calibration.assert_not_called()


@pytest.mark.parametrize("task_type", [CreateEFHPIPulse, CreateEFPIPulse])
def test_create_ef_pulse_tasks_group_rabi_context_in_ui(
    task_type: type[CreateEFHPIPulse | CreateEFPIPulse],
) -> None:
    for name in (
        "ef_rabi_amplitude",
        "ef_rabi_frequency",
        "ef_rabi_phase",
        "ef_rabi_offset",
        "ef_rabi_angle",
        "ef_rabi_noise",
        "ef_rabi_distance",
        "ef_rabi_reference_phase",
        "ef_rabi_r2",
    ):
        spec = task_type.input_spec[name]
        assert spec.ui_group == "EF Rabi normalization"
        assert spec.ui_group_collapsed is True


def test_ef_readout_classification_builds_three_state_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = EFReadoutClassification()
    _set_inputs(task)
    exp = _experiment()
    figures = {f"Q00_prepared_{state}": go.Figure() for state in range(3)}
    exp.build_classifier.return_value = SimpleNamespace(
        data={
            "average_readout_fidelity": {"Q00": 0.91},
            "readout_fidelities": {"Q00": [0.95, 0.9, 0.88]},
        },
        figures=figures,
    )
    save_calibration = MagicMock()
    monkeypatch.setattr(task, "save_calibration", save_calibration)

    run_result = task.run(_backend(exp), "0")
    processed = task.postprocess(_backend(exp), "exec", run_result, "0")

    kwargs = exp.build_classifier.call_args.kwargs
    assert exp.applied_frequencies == [{"Q00_ge": 5.0, "Q00-ef": 4.7, "Q00_read": 6.1}]
    assert kwargs["targets"] == "Q00"
    assert kwargs["n_states"] == 3
    assert kwargs["save_dir"] == exp.classifier_dir
    assert processed.output_parameters["average_ef_readout_fidelity"].value == 0.91
    assert processed.output_parameters["ef_readout_fidelity_f"].value == 0.88
    assert processed.figures == list(figures.values())
    assert processed.validation_error is None
    save_calibration.assert_called_once()


def test_qubex_package_registers_all_ef_calibration_tasks() -> None:
    import qdash.workflow.calibtasks.qubex  # noqa: F401
    from qdash.workflow.calibtasks.base import BaseTask

    assert BaseTask.registry["qubex"]["CheckEFRabi"] is CheckEFRabi
    assert BaseTask.registry["qubex"]["CreateEFHPIPulse"] is CreateEFHPIPulse
    assert BaseTask.registry["qubex"]["CreateEFPIPulse"] is CreateEFPIPulse
    assert BaseTask.registry["qubex"]["EFReadoutClassification"] is EFReadoutClassification
