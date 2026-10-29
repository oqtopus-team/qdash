"""Tests for coupling strength measurement and persistence."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, create_autospec, patch

import numpy as np
import plotly.graph_objects as go
import pytest
from qubex import Experiment

from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.two_qubit.check_coupling_strength import CheckCouplingStrength
from qdash.workflow.engine.task.backend_saver import BackendSaver


@pytest.fixture
def task_and_experiment(monkeypatch):
    task = CheckCouplingStrength()
    exp = MagicMock()
    exp.get_qubit_label.side_effect = lambda qid: f"Q{qid:02d}"
    pulses = {"Q00": MagicMock(), "Q01": MagicMock()}
    exp.hpi_pulse = pulses
    monkeypatch.setattr(task, "get_experiment", lambda backend: exp)
    return task, exp


def test_run_passes_pulses_sweep_and_returns_r2(task_and_experiment) -> None:
    task, exp = task_and_experiment
    pulses = exp.hpi_pulse
    raw = SimpleNamespace(data={"g": 0.005, "r2": 0.96})
    # Bind the method signature so invalid keyword arguments fail the test.
    exp.obtain_coupling_strength = create_autospec(
        Experiment.__new__(Experiment).obtain_coupling_strength, return_value=raw
    )
    result = task.run(cast("Any", object()), "0-1")

    kwargs = exp.obtain_coupling_strength.call_args.kwargs
    assert kwargs["target_qubit"] == "Q00"
    assert kwargs["spectator_qubit"] == "Q01"
    assert kwargs["x90"] == {"Q00": pulses["Q00"]}
    assert kwargs["x180"] == {label: pulse.repeated.return_value for label, pulse in pulses.items()}
    for pulse in pulses.values():
        pulse.repeated.assert_called_once_with(2)
    np.testing.assert_array_equal(kwargs["time_range"], np.arange(0, 20001, 400))
    assert kwargs["n_shots"] == task.run_parameters["shots"].get_value()
    assert kwargs["shot_interval"] == task.run_parameters["interval"].get_value()
    assert kwargs["plot"] is False
    assert result.raw_result is raw
    assert result.r2 == {"0-1": 0.96}
    exp.modified_frequencies.assert_not_called()
    assert exp.ctx.mock_calls == []


@pytest.mark.parametrize("strength", [0.005, 0.0])
def test_postprocess_converts_coupling_strength_to_mhz(strength: float) -> None:
    task = CheckCouplingStrength()
    figure = go.Figure()
    result = task.postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(
            raw_result=SimpleNamespace(data={"g": strength, "zeta": -0.00002, "fig": figure})
        ),
        "0-1",
    )

    metric = result.output_parameters["qubit_qubit_coupling_strength"]
    assert metric.value == pytest.approx(strength * 1e3)
    assert metric.unit == "MHz"
    assert metric.qid_role == "coupling"
    assert metric.execution_id == "exec-1"
    assert result.figures == [figure]
    assert result.validation_error is None


@pytest.mark.parametrize("strength", [None, np.nan, np.inf, -np.inf, -0.005])
def test_postprocess_rejects_invalid_strength(strength: float | None) -> None:
    result = CheckCouplingStrength().postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"g": strength, "zeta": -0.00002})),
        "0-1",
    )
    assert result.validation_error is not None
    assert "qubit_qubit_coupling_strength" in result.validation_error


def test_registered_task_saves_both_coupling_metrics() -> None:
    task = generate_task_instances(
        ["CheckCouplingStrength"], {"CheckCouplingStrength": {}}, "qubex"
    )["CheckCouplingStrength"]
    output = task.postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"g": 0.005, "zeta": -0.00002})),
        "0-1",
    ).output_parameters
    state_manager = MagicMock()
    state_manager.get_task.return_value = SimpleNamespace(output_parameters=output)
    execution = SimpleNamespace(execution_id="exec-1", chip_id="chip-1", project_id="proj-1")
    backend = MagicMock(name="backend")
    backend.name = "qubex"
    saver = BackendSaver(state_manager, "alice", "/tmp/calib", "tm-1")

    with patch("qdash.repository.MongoCouplingCalibrationRepository") as repository:
        repository.return_value.get_calibration_data_for_update.return_value = {}
        saver.save(task, cast("Any", execution), "0-1", backend, success=True)

    saved = repository.return_value.update_calib_data.call_args.kwargs
    assert saved["qid"] == "0-1"
    assert saved["project_id"] == "proj-1"
    assert saved["output_parameters"]["qubit_qubit_coupling_strength"].value == pytest.approx(5.0)
    assert saved["output_parameters"]["qubit_qubit_coupling_strength"].unit == "MHz"

    assert saved["output_parameters"]["static_zz_interaction"].value == pytest.approx(-20.0)
    assert saved["output_parameters"]["static_zz_interaction"].unit == "KHz"


@pytest.mark.parametrize("zeta", [0.00002, -0.00002, 0.0])
def test_postprocess_converts_signed_static_zz_to_khz(zeta) -> None:
    result = CheckCouplingStrength().postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"g": 0.005, "zeta": zeta})),
        "0-1",
    )
    metric = result.output_parameters["static_zz_interaction"]
    assert metric.value == pytest.approx(zeta * 1e6)
    assert metric.unit == "KHz"
    assert metric.qid_role == "coupling"
    assert metric.execution_id == "exec-1"
    assert result.validation_error is None


@pytest.mark.parametrize("zeta", [None, np.nan, np.inf, -np.inf])
def test_postprocess_rejects_missing_or_non_finite_static_zz(zeta) -> None:
    result = CheckCouplingStrength().postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"g": 0.005, "zeta": zeta})),
        "0-1",
    )
    assert result.validation_error is not None
    assert "static_zz_interaction" in result.validation_error
