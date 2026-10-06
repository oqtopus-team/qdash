"""Tests for JAZZ measurement and static ZZ metric persistence."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.two_qubit.check_jazz import CheckJAZZ
from qdash.workflow.engine.task.backend_saver import BackendSaver


def test_run_passes_pulses_sweep_and_returns_r2(monkeypatch) -> None:
    task = CheckJAZZ()
    exp = MagicMock()
    exp.get_qubit_label.side_effect = lambda qid: f"Q{qid:02d}"
    pulses = {"Q00": MagicMock(), "Q01": MagicMock()}
    exp.hpi_pulse = pulses
    raw = SimpleNamespace(data={"zeta": -0.00002, "r2": 0.96})
    exp.jazz_experiment.return_value = raw
    monkeypatch.setattr(task, "get_experiment", lambda backend: exp)

    result = task.run(cast("Any", object()), "0-1")

    kwargs = exp.jazz_experiment.call_args.kwargs
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


@pytest.mark.parametrize("zeta", [0.00002, -0.00002, 0.0])
def test_postprocess_converts_signed_zz_to_khz(zeta: float) -> None:
    task = CheckJAZZ()
    figure = go.Figure()
    result = task.postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"zeta": zeta, "xi": zeta / 2, "fig": figure})),
        "0-1",
    )

    metric = result.output_parameters["static_zz_interaction"]
    assert metric.value == pytest.approx(zeta * 1e6)
    assert metric.unit == "KHz"
    assert metric.qid_role == "coupling"
    assert metric.execution_id == "exec-1"
    assert result.figures == [figure]
    assert result.validation_error is None


@pytest.mark.parametrize("zeta", [None, np.nan, np.inf, -np.inf])
def test_postprocess_rejects_missing_or_non_finite_zz(zeta: float | None) -> None:
    result = CheckJAZZ().postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"zeta": zeta})),
        "0-1",
    )
    assert result.validation_error is not None
    assert "static_zz_interaction" in result.validation_error


def test_registered_task_saves_static_zz_to_coupling_metric() -> None:
    task = generate_task_instances(["CheckJAZZ"], {"CheckJAZZ": {}}, "qubex")["CheckJAZZ"]
    output = task.postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"zeta": -0.00002})),
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
    assert saved["output_parameters"]["static_zz_interaction"].value == pytest.approx(-20.0)
    assert saved["output_parameters"]["static_zz_interaction"].unit == "KHz"
