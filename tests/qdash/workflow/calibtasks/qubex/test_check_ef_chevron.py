"""Tests for EF chevron execution and qubit metric persistence."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.common.config.metrics import load_metrics_config
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_fine.check_ef_chevron import CheckEFChevron
from qdash.workflow.engine.task.backend_saver import BackendSaver


def _task() -> CheckEFChevron:
    task = CheckEFChevron()
    for name, value in {
        "qubit_frequency": 5.0,
        "control_frequency": 5.001,
        "drag_pi_amplitude": 0.1,
        "drag_pi_duration": 32.0,
        "drag_pi_beta": -0.5,
        "readout_frequency": 6.1,
        "readout_amplitude": 0.031,
    }.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    return task


def _backend() -> Any:
    return SimpleNamespace(
        get_instance=lambda: SimpleNamespace(
            get_qubit_label=lambda qid: f"Q{qid:02d}",
            ctx=SimpleNamespace(resolve_ef_label=lambda label: f"{label}_ef"),
        )
    )


def _result(frequency=4.72, ratio=8.5, figures=None) -> RunResult:
    return RunResult(
        raw_result=SimpleNamespace(
            data={
                "resonant_frequencies": {"Q00_ef": frequency},
                "peak_background_rms_ratios": {"Q00_ef": ratio},
            },
            figures=figures or {},
        )
    )


def test_run_passes_ef_seed_sweep_and_amplitude(monkeypatch) -> None:
    task = _task()
    exp = MagicMock()
    exp.get_qubit_label.return_value = "Q00"
    exp.ctx.resolve_ge_label.return_value = "Q00_ge"
    exp.ctx.resolve_read_label.return_value = "Q00_read"
    exp.modified_frequencies.return_value = nullcontext()
    monkeypatch.setattr(task, "get_experiment", lambda backend: exp)
    estimate = MagicMock(return_value=_result().raw_result)
    with patch(
        "qdash.workflow.calibtasks.qubex.one_qubit_fine.check_ef_chevron."
        "estimate_ef_frequency_from_chevron",
        estimate,
    ):
        result = task.run(cast("Any", object()), "0")
    kwargs = estimate.call_args.kwargs
    assert kwargs["targets"] == ["Q00"]
    assert kwargs["frequencies"] == {"Q00": 4.7}
    assert kwargs["amplitudes"] == {"Q00": 0.0625}
    np.testing.assert_allclose(kwargs["detuning_range"], np.linspace(-0.05, 0.05, 41))
    assert list(kwargs["time_range"]) == list(range(0, 257, 8))
    assert kwargs["n_shots"] == 256
    assert kwargs["shot_interval"] == task.run_parameters["interval"].get_value()
    assert kwargs["plot"] is False and kwargs["save_image"] is False
    assert result.raw_result is estimate.return_value
    exp.params.readout_amplitude.__setitem__.assert_called_once_with("Q00", 0.031)
    exp.modified_frequencies.assert_called_once_with({"Q00_ge": 5.001, "Q00_read": 6.1})


def test_postprocess_uses_measured_ge_and_returns_qubex_figures() -> None:
    figure = go.Figure()
    result = _task().postprocess(
        _backend(), "exec-1", _result(figures={"measurement": figure}), "0"
    )
    assert result.validation_error is None
    assert result.output_parameters["ef_frequency"].value == 4.72
    assert result.output_parameters["anharmonicity"].value == pytest.approx(-0.28)
    assert all(
        p.unit == "GHz" and p.execution_id == "exec-1" for p in result.output_parameters.values()
    )
    assert result.figures == [figure]


@pytest.mark.parametrize(
    "frequency,ratio",
    [(None, 8.5), (np.nan, 8.5), (np.inf, 8.5), (5.01, 8.5), (4.72, None), (4.72, 4.99)],
)
def test_postprocess_rejects_invalid_measurements(frequency, ratio) -> None:
    result = _task().postprocess(_backend(), "exec-1", _result(frequency, ratio), "0")
    assert result.validation_error is not None


def test_registered_task_saves_both_qubit_metrics() -> None:
    task = generate_task_instances(["CheckEFChevron"], {"CheckEFChevron": {}}, "qubex")[
        "CheckEFChevron"
    ]
    task.input_parameters["qubit_frequency"] = InputParameterModel(value=5.0)
    output = task.postprocess(_backend(), "exec-1", _result(), "0").output_parameters
    state_manager = MagicMock()
    state_manager.get_task.return_value = SimpleNamespace(output_parameters=output)
    execution = SimpleNamespace(execution_id="exec-1", chip_id="chip-1", project_id="proj-1")
    backend = MagicMock()
    backend.name = "qubex"
    saver = BackendSaver(state_manager, "alice", "/tmp/calib", "tm-1")
    with patch("qdash.repository.MongoQubitCalibrationRepository") as repository:
        repository.return_value.get_calibration_data_for_update.return_value = {}
        saver.save(task, cast("Any", execution), "0", backend, success=True)
    saved = repository.return_value.update_calib_data.call_args.kwargs
    assert saved["qid"] == "0" and saved["project_id"] == "proj-1"
    assert saved["output_parameters"]["ef_frequency"].value == 4.72
    assert saved["output_parameters"]["anharmonicity"].value == pytest.approx(-0.28)
    metrics = load_metrics_config().qubit_metrics
    assert metrics["ef_frequency"].unit == "GHz" and metrics["ef_frequency"].scale == 1
    assert metrics["anharmonicity"].unit == "MHz" and metrics["anharmonicity"].scale == 1000
