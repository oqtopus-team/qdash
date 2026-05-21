from contextlib import nullcontext
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import plotly.graph_objects as go
import pytest

from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_chevron import CheckChevron

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any


class _DummyExperiment:
    def __init__(self) -> None:
        self.params = SimpleNamespace(readout_amplitude={"Q00": 0.0})

    def get_qubit_label(self, qid: int) -> str:
        assert qid == 0
        return "Q00"

    def modified_frequencies(self, _frequencies: dict[str, float]):
        return nullcontext()


def test_check_chevron_run_uses_adaptive_helper(monkeypatch) -> None:
    task = CheckChevron()
    task.input_parameters["coarse_qubit_frequency"] = ParameterModel(value=4.25, unit="GHz")
    task.input_parameters["readout_frequency"] = ParameterModel(value=6.1, unit="GHz")
    task.input_parameters["readout_amplitude"] = ParameterModel(value=0.031, unit="a.u.")
    task.input_parameters["coarse_control_amplitude"] = ParameterModel(value=0.07, unit="a.u.")

    exp = _DummyExperiment()
    captured: dict[str, object] = {}

    def fake_get_experiment(_backend):
        return exp

    def fake_save_calibration(_backend):
        return None

    def fake_estimate_qubit_frequency_from_chevron_adaptive(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            data={
                "resonant_frequencies": {"Q00": 4.321},
                "amplitudes_used": {"Q00": 0.082},
                "omega_rabis": {"Q00": 0.011},
                "peak_prominence_ratios": {"Q00": 1.5},
            },
            figures={
                "Q00_measurement": go.Figure(),
                "Q00_transform": go.Figure(),
            },
        )

    monkeypatch.setattr(task, "get_experiment", fake_get_experiment)
    monkeypatch.setattr(task, "save_calibration", fake_save_calibration)
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_chevron."
        "estimate_qubit_frequency_from_chevron_adaptive",
        fake_estimate_qubit_frequency_from_chevron_adaptive,
    )

    result = task.run(backend=cast("QubexBackend", object()), qid="0")

    assert captured["exp"] is exp
    assert captured["targets"] == ["Q00"]
    assert captured["frequencies"] == {"Q00": 4.25}
    assert captured["amplitudes"] == {"Q00": 0.07}
    assert captured["plot"] is False
    assert captured["save_image"] is False
    assert result.raw_result["resonant_frequencies"]["Q00"] == 4.321
    assert result.raw_result["control_amplitude_used"] == 0.082
    assert result.raw_result["readout_amplitude_used"] == 0.031


def test_check_chevron_postprocess_handles_adaptive_figures(monkeypatch) -> None:
    task = CheckChevron()
    task.input_parameters["readout_amplitude"] = ParameterModel(value=0.031, unit="a.u.")

    monkeypatch.setattr(task, "get_experiment", lambda _backend: object())
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    run_result = RunResult(
        raw_result={
            "resonant_frequencies": {"Q00": 4.321},
            "control_amplitude_used": 0.082,
            "readout_amplitude_used": 0.031,
            "figures": {
                "Q00_measurement": go.Figure(),
                "Q00_transform": go.Figure(),
                "Q00_rough_measurement": go.Figure(),
                "Q00_rough_transform": go.Figure(),
            },
        }
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=run_result,
        qid="0",
    )

    assert result.output_parameters["qubit_frequency"].value == 4.321
    assert result.output_parameters["control_amplitude"].value == 0.082
    assert "readout_amplitude" not in result.output_parameters
    assert len(result.figures) == 5


def test_check_chevron_run_requires_db_readout_amplitude(monkeypatch) -> None:
    task = CheckChevron()
    task.input_parameters["coarse_qubit_frequency"] = ParameterModel(value=4.25, unit="GHz")
    task.input_parameters["readout_frequency"] = ParameterModel(value=6.1, unit="GHz")
    task.input_parameters["readout_amplitude"] = None

    monkeypatch.setattr(task, "get_experiment", lambda _backend: _DummyExperiment())

    with pytest.raises(ValueError, match="readout_amplitude input parameter is required"):
        task.run(backend=cast("QubexBackend", object()), qid="0")
