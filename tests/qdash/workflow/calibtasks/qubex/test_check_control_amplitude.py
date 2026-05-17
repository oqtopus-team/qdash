from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, cast

import plotly.graph_objects as go

from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_control_amplitude import CheckControlAmplitude

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any


def test_check_control_amplitude_floors_output_to_coarse_input(monkeypatch) -> None:
    task = CheckControlAmplitude()
    task.input_parameters["coarse_control_amplitude"] = ParameterModel(value=0.02, unit="a.u.")

    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "Q00": {
                    "estimated_amplitude": 0.008,
                    "rabi_rate": 0.012,
                    "f0": 4.321,
                    "r2": 0.98,
                    "fig": go.Figure(),
                }
            }
        ),
        qid="0",
    )

    assert result.output_parameters["control_amplitude"].value == 0.02
    assert result.output_parameters["coarse_control_amplitude"].value == 0.02


def test_check_control_amplitude_updates_refined_coarse_seed(monkeypatch) -> None:
    task = CheckControlAmplitude()
    task.input_parameters["coarse_control_amplitude"] = ParameterModel(value=0.02, unit="a.u.")

    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "Q00": {
                    "estimated_amplitude": 0.035,
                    "rabi_rate": 0.012,
                    "f0": 4.321,
                    "r2": 0.98,
                    "fig": go.Figure(),
                }
            }
        ),
        qid="0",
    )

    assert result.output_parameters["control_amplitude"].value == 0.035
    assert result.output_parameters["coarse_control_amplitude"].value == 0.035


def test_check_control_amplitude_run_uses_coarse_control_amplitude_without_extra_uplift(
    monkeypatch,
) -> None:
    task = CheckControlAmplitude()
    task.input_parameters["coarse_qubit_frequency"] = ParameterModel(value=4.25, unit="GHz")
    task.input_parameters["readout_frequency"] = ParameterModel(value=6.1, unit="GHz")
    task.input_parameters["readout_amplitude"] = ParameterModel(value=0.031, unit="a.u.")
    task.input_parameters["coarse_control_amplitude"] = ParameterModel(value=0.07, unit="a.u.")

    captured: dict[str, object] = {}

    class _DummyExperiment:
        def measure_qubit_resonance(self, label: str, **kwargs):
            captured["label"] = label
            captured.update(kwargs)
            return {}

        def modified_frequencies(self, _frequencies: dict[str, float]):
            return nullcontext()

    monkeypatch.setattr(task, "get_experiment", lambda _backend: _DummyExperiment())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(task, "get_resonator_label", lambda _backend, _qid: "RQ00")
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    task.run(backend=cast("QubexBackend", object()), qid="0")

    assert captured["label"] == "Q00"
    assert captured["control_amplitude"] == 0.07
    assert captured["readout_amplitude"] == 0.031
