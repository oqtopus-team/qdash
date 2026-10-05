"""Tests for the fixed-grid CheckChevron task."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_chevron import CheckChevron

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any


class _DummyExperiment:
    def __init__(self) -> None:
        self.params = SimpleNamespace(readout_amplitude={"Q00": 0.0})
        self.modified_frequency_calls: list[dict[str, float]] = []
        self.chevron_kwargs: dict[str, Any] = {}

    def get_qubit_label(self, qid: int) -> str:
        assert qid == 0
        return "Q00"

    def modified_frequencies(self, frequencies: dict[str, float]):
        self.modified_frequency_calls.append(frequencies)
        return nullcontext()

    def chevron_pattern(self, **kwargs: Any) -> Any:
        self.chevron_kwargs = kwargs
        return SimpleNamespace(
            data={
                "resonant_frequencies": {"Q00": 4.321},
                "rabi_fit_r2": {"Q00": np.array([0.91, 0.89, 0.87])},
            },
            figures={"Q00": go.Figure()},
        )


def _configured_task() -> CheckChevron:
    task = CheckChevron()
    task.input_parameters["control_frequency"] = InputParameterModel(value=4.25, unit="GHz")
    task.input_parameters["readout_frequency"] = InputParameterModel(value=6.1, unit="GHz")
    task.input_parameters["readout_amplitude"] = InputParameterModel(value=0.031, unit="a.u.")
    task.input_parameters["control_amplitude"] = InputParameterModel(value=0.07, unit="a.u.")
    return task


def test_check_chevron_run_executes_one_fixed_grid_sweep(monkeypatch) -> None:
    task = _configured_task()
    experiment = _DummyExperiment()
    monkeypatch.setattr(task, "get_experiment", lambda _backend: experiment)
    monkeypatch.setattr(task, "save_calibration", lambda _backend: None)

    result = task.run(backend=cast("QubexBackend", object()), qid="0")

    assert result.raw_result.data["resonant_frequencies"]["Q00"] == 4.321
    assert result.r2 == pytest.approx({"0": 0.89})
    assert experiment.modified_frequency_calls == [{"Q00": 4.25, "RQ00": 6.1}]
    assert experiment.params.readout_amplitude["Q00"] == 0.031
    assert experiment.chevron_kwargs["targets"] == ["Q00"]
    assert experiment.chevron_kwargs["frequencies"] == {"Q00": 4.25}
    assert experiment.chevron_kwargs["amplitudes"] == {"Q00": 0.07}
    np.testing.assert_allclose(
        experiment.chevron_kwargs["detuning_range"], np.linspace(-0.05, 0.05, 51)
    )
    assert list(experiment.chevron_kwargs["time_range"]) == list(range(0, 401, 8))
    assert experiment.chevron_kwargs["n_shots"] == 1024
    assert experiment.chevron_kwargs["shot_interval"] == 153600.0
    assert experiment.chevron_kwargs["plot"] is False
    assert experiment.chevron_kwargs["save_image"] is False


def test_check_chevron_postprocess_extracts_frequency_and_figures(monkeypatch) -> None:
    task = _configured_task()
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    raw_result = SimpleNamespace(
        data={"resonant_frequencies": {"Q00": 4.321}},
        figures={"Q00": go.Figure()},
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result=raw_result),
        qid="0",
    )

    assert result.output_parameters["qubit_frequency"].value == 4.321
    assert result.output_parameters["qubit_frequency"].execution_id == "exec-1"
    assert len(result.figures) == 2
    assert result.validation_error is None


def test_check_chevron_requires_calibrated_control_frequency(monkeypatch) -> None:
    task = _configured_task()
    task.input_parameters["control_frequency"] = InputParameterModel(value=None)
    monkeypatch.setattr(task, "get_experiment", lambda _backend: _DummyExperiment())

    with pytest.raises(ValueError, match="control_frequency input parameter is required"):
        task.run(backend=cast("QubexBackend", object()), qid="0")


def test_check_chevron_r2_ignores_non_finite_fits() -> None:
    result = SimpleNamespace(data={"rabi_fit_r2": {"Q00": np.array([0.92, np.nan, np.inf, 0.88])}})

    assert CheckChevron._mean_rabi_fit_r2(result, "Q00") == pytest.approx(0.9)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"rabi_fit_r2": {}},
        {"rabi_fit_r2": {"Q00": np.array([])}},
        {"rabi_fit_r2": {"Q00": np.array([np.nan, np.inf])}},
    ],
)
def test_check_chevron_r2_is_missing_without_finite_fits(data: dict[str, Any]) -> None:
    assert CheckChevron._mean_rabi_fit_r2(SimpleNamespace(data=data), "Q00") is None
