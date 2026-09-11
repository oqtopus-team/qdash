"""Tests for restoring Rabi context before HPI pulse calibration."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import plotly.graph_objects as go
import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.create_hpi_pulse import CreateHPIPulse
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.create_pi_pulse import CreatePIPulse
from qdash.workflow.calibtasks.qubex.one_qubit_fine.create_drag_hpi_pulse import (
    CreateDRAGHPIPulse,
)
from qdash.workflow.calibtasks.qubex.one_qubit_fine.create_drag_pi_pulse import (
    CreateDRAGPIPulse,
)
from qdash.workflow.calibtasks.qubex.two_qubit.create_zx90 import CreateZX90

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend


RABI_INPUTS = {
    "qubit_frequency": 5.0,
    "control_amplitude": 0.025,
    "readout_amplitude": 0.2,
    "readout_frequency": 7.0,
    "rabi_amplitude": 0.45,
    "rabi_phase": 0.1,
    "rabi_offset": 0.2,
    "rabi_angle": 180.0,
    "rabi_noise": 0.01,
    "rabi_distance": 0.9,
    "rabi_reference_phase": 0.3,
    "rabi_r2": 0.98,
    "maximum_rabi_frequency": 800.0,
}

RABI_DEPENDENCIES = set(RABI_INPUTS) - {
    "qubit_frequency",
    "readout_amplitude",
    "readout_frequency",
}


def _configured_task() -> CreateHPIPulse:
    task = CreateHPIPulse()
    for name, value in RABI_INPUTS.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    return task


def _backend_for(exp: object) -> SimpleNamespace:
    return SimpleNamespace(get_instance=lambda: exp)


class RecordingExperiment:
    def __init__(self, initial_rabi_context: object) -> None:
        self.rabi_context: object = initial_rabi_context
        self.context_at_calibration: Any = None
        self.params = SimpleNamespace(readout_amplitude={}, control_amplitude={})

    def get_qubit_label(self, _qid: int) -> str:
        return "Q01"

    def store_rabi_params(self, params: dict[str, object]) -> None:
        self.rabi_context = params

    def calibrate_hpi_pulse(self, **_kwargs: Any) -> Any:
        self.context_at_calibration = self.rabi_context
        return SimpleNamespace(data={"Q01": SimpleNamespace(r2=0.99)})


class PostprocessExperiment:
    def get_qubit_label(self, _qid: int) -> str:
        return "Q01"


class PulseCalibrationData:
    calib_value = 0.25

    @staticmethod
    def fit() -> dict[str, go.Figure]:
        return {"fig": go.Figure()}


def test_run_restores_same_rabi_context_for_same_and_split_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts = []
    for initial_context in ({"Q01": "same-session-value"}, {}):
        task = _configured_task()
        exp = RecordingExperiment(initial_context)
        backend = _backend_for(exp)
        monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

        task.run(cast("QubexBackend", backend), "1")
        contexts.append(exp.context_at_calibration["Q01"])

    assert contexts[0] == contexts[1]
    assert contexts[0].frequency == pytest.approx(0.02)
    assert contexts[0].amplitude == pytest.approx(RABI_INPUTS["rabi_amplitude"])
    assert contexts[0].r2 == pytest.approx(RABI_INPUTS["rabi_r2"])


def test_preprocess_fails_explicitly_when_rabi_inputs_are_missing() -> None:
    task = CreateHPIPulse()
    backend = SimpleNamespace(config={})

    with pytest.raises(ValueError, match="CreateHPIPulse requires resolved calibration inputs"):
        task.preprocess(cast("QubexBackend", backend), "1")


def test_hpi_duration_is_used_consistently_for_run_and_output_parameters() -> None:
    task = CreateHPIPulse({"run_parameters": {"hpi_duration": {"value": 52, "value_type": "int"}}})

    result = task.postprocess(
        cast("QubexBackend", _backend_for(PostprocessExperiment())),
        "execution-id",
        RunResult(raw_result=SimpleNamespace(data={"Q01": PulseCalibrationData()})),
        "1",
    )

    assert CreateHPIPulse.output_spec["hpi_duration"].default is None
    assert result.output_parameters["hpi_duration"].value == 52


@pytest.mark.parametrize(
    ("task_type", "run_name", "output_name", "duration"),
    [
        (CreatePIPulse, "pi_duration", "pi_duration", 40),
        (CreateDRAGHPIPulse, "drag_hpi_duration", "drag_hpi_duration", 20),
        (CreateDRAGPIPulse, "drag_pi_duration", "drag_pi_duration", 28),
    ],
)
def test_create_pulse_publishes_effective_duration(
    task_type: type[CreatePIPulse],
    run_name: str,
    output_name: str,
    duration: int,
) -> None:
    task = task_type({"run_parameters": {run_name: {"value": duration, "value_type": "int"}}})
    if task_type is CreatePIPulse:
        raw_result = SimpleNamespace(data={"Q01": PulseCalibrationData()})
    else:
        raw_result = {
            "beta": {"Q01": 0.1},
            "amplitude": {"Q01": {"amplitude": 0.25, "fig": go.Figure()}},
        }

    result = task.postprocess(
        cast("QubexBackend", _backend_for(PostprocessExperiment())),
        "execution-id",
        RunResult(raw_result=raw_result),
        "1",
    )

    assert task_type.output_spec[output_name].default is None
    assert result.output_parameters[output_name].value == duration


def test_restore_rabi_context_rejects_low_quality_database_value() -> None:
    task = _configured_task()
    task.input_parameters["rabi_r2"] = InputParameterModel(value=0.59)
    exp = RecordingExperiment({"Q01": "previous-valid-context"})

    with pytest.raises(ValueError, match=r"rabi_r2 greater than or equal to 0\.6"):
        task._restore_rabi_context(cast("QubexBackend", _backend_for(exp)), "1")

    assert exp.rabi_context == {"Q01": "previous-valid-context"}


@pytest.mark.parametrize(
    "task_type",
    [CreateHPIPulse, CreatePIPulse, CreateDRAGHPIPulse, CreateDRAGPIPulse],
)
def test_rabi_dependent_create_tasks_require_complete_database_context(
    task_type: type[CreateHPIPulse],
) -> None:
    assert set(task_type.input_spec) >= RABI_DEPENDENCIES
    assert all(
        task_type.input_spec[name].resolution == "database_required" for name in RABI_DEPENDENCIES
    )


def test_create_zx90_requires_complete_cr_database_context() -> None:
    cr_dependencies = {
        "cr_duration",
        "cr_amplitude",
        "cr_phase",
        "cr_beta",
        "cancel_amplitude",
        "cancel_phase",
        "cancel_beta",
        "rotary_amplitude",
        "zx_rotation_rate",
        "cr_ramptime",
    }

    assert all(
        CreateZX90.input_spec[name].resolution == "database_required" for name in cr_dependencies
    )
