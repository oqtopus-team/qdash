import copy
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import plotly.graph_objects as go
import pytest

from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy import CheckQubitSpectroscopy

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend
else:
    QubexBackend = Any


def test_check_qubit_spectroscopy_outputs_uplifted_coarse_control_amplitude_and_marks_it(
    monkeypatch,
) -> None:
    task = CheckQubitSpectroscopy()
    raw_fig = go.Figure(go.Heatmap(x=[4.0, 4.1], y=[-20.0, -10.0], z=[[0.0, 1.0], [1.0, 0.0]]))
    marked_fig = go.Figure(raw_fig)
    freq_result = SimpleNamespace(
        f01=SimpleNamespace(
            frequency=4.321,
            repr_db=-20.0,
            quality_level=4,
        ),
        f12=None,
        anharmonicity=None,
    )

    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy."
        "estimate_and_mark_qubit_figure",
        lambda *_args, **_kwargs: (marked_fig, freq_result),
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result={"Q00": {"fig": raw_fig}}),
        qid="0",
    )

    assert result.output_parameters["coarse_qubit_frequency"].value == 4.321
    assert result.output_parameters["f01_repr_db"].value == -20.0
    assert result.output_parameters["coarse_control_amplitude"].value == pytest.approx(
        10 ** (-10 / 20)
    )
    assert len(result.figures[0].layout.shapes) == 1
    assert result.figures[0].layout.shapes[-1]["y0"] == pytest.approx(-10.0)
    assert result.figures[0].layout.shapes[-1]["y1"] == pytest.approx(-10.0)


def test_check_qubit_spectroscopy_does_not_output_invalid_frequency(monkeypatch) -> None:
    task = CheckQubitSpectroscopy()
    raw_fig = go.Figure(go.Heatmap(x=[4.0, 4.1], y=[-20.0, -10.0], z=[[0.0, 1.0], [1.0, 0.0]]))
    marked_fig = go.Figure(raw_fig)
    freq_result = SimpleNamespace(
        f01=SimpleNamespace(
            frequency=0.0,
            repr_db=-20.0,
            quality_level=1,
        ),
        f12=None,
        anharmonicity=None,
    )

    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")
    monkeypatch.setattr(
        "qdash.workflow.calibtasks.qubex.cw.check_qubit_spectroscopy."
        "estimate_and_mark_qubit_figure",
        lambda *_args, **_kwargs: (marked_fig, freq_result),
    )

    result = task.postprocess(
        backend=cast("QubexBackend", object()),
        execution_id="exec-1",
        run_result=RunResult(raw_result={"Q00": {"fig": raw_fig}}),
        qid="0",
    )

    assert result.output_parameters == {}
    assert result.validation_error is not None


def test_frequency_range_is_resolved_from_control_box_when_unset(monkeypatch) -> None:
    task = CheckQubitSpectroscopy()
    backend = cast("QubexBackend", object())
    exp = MagicMock()
    exp.ctx.experiment_system.get_control_box_for_qubit.return_value = SimpleNamespace(
        traits=SimpleNamespace(default_control_frequency_range=(3.0, 5.75, 0.005))
    )
    monkeypatch.setattr(task, "get_experiment", lambda _backend: exp)
    monkeypatch.setattr(task, "get_qubit_label", lambda _backend, _qid: "Q00")

    task.resolve_run_parameters(backend, "0")

    assert task.run_parameters["frequency_range"].value == (3.0, 5.75, 0.005)
    exp.ctx.experiment_system.get_control_box_for_qubit.assert_called_once_with("Q00")


def test_run_parameters_only_expose_measurement_settings() -> None:
    assert set(CheckQubitSpectroscopy.run_spec) == {"frequency_range", "readout_amplitude"}


def test_frequency_range_can_be_overridden_per_task() -> None:
    task = CheckQubitSpectroscopy()
    task.run_parameters = copy.deepcopy(task.run_parameters)
    task.run_parameters["frequency_range"].value = (3.0, 3.3, 0.1)

    assert list(task._frequency_range()) == pytest.approx([3.0, 3.1, 3.2])


def test_explicit_frequency_range_is_not_resolved_from_control_box() -> None:
    task = CheckQubitSpectroscopy()
    task.run_parameters["frequency_range"].value = (3.0, 3.3, 0.1)
    backend = cast("QubexBackend", MagicMock())

    task.resolve_run_parameters(backend, "0")

    backend.get_experiment.assert_not_called()
