"""Tests for FH chevron execution and frequency persistence."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, create_autospec, patch

import numpy as np
import plotly.graph_objects as go
import pytest
from qubex.contrib.experiment import estimate_fh_frequency_from_chevron_adaptive

from qdash.common.config.metrics import load_metrics_config
from qdash.common.config.params_updater import resolve_param_yaml_file_names
from qdash.datamodel.task import InputParameterModel
from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.one_qubit_fine.check_adaptive_fh_chevron import (
    CheckAdaptiveFHChevron,
)
from qdash.workflow.engine.task.backend_saver import BackendSaver


def _task() -> CheckAdaptiveFHChevron:
    task = CheckAdaptiveFHChevron()
    for name, value in {
        "control_frequency": 5.001,
        "control_frequency_ef": 4.72,
        "control_amplitude": 0.12,
        "hpi_amplitude": 0.1,
        "hpi_duration": 32.0,
        "ef_pi_amplitude": 0.08,
        "ef_pi_duration": 32.0,
        "readout_frequency": 6.1,
        "readout_amplitude": 0.031,
    }.items():
        task.input_parameters[name] = InputParameterModel(value=value)
    return task


def _backend() -> Any:
    return SimpleNamespace(
        get_instance=lambda: SimpleNamespace(
            get_qubit_label=lambda qid: f"Q{qid:02d}",
            ctx=SimpleNamespace(resolve_fh_label=lambda label: f"{label}-fh"),
        )
    )


def _result(frequency=4.44, ratio=8.5, figures=None) -> RunResult:
    return RunResult(
        raw_result=SimpleNamespace(
            data={
                "search_results": {"Q00-fh": {"omega_q": 4.43}},
                "resonant_frequencies": {"Q00-fh": frequency},
                "peak_background_rms_ratios": {"Q00-fh": ratio},
            },
            figures=figures or {},
        )
    )


def _experiment(configured_fh_frequency: float | None = 4.44) -> MagicMock:
    exp = MagicMock()
    exp.get_qubit_label.return_value = "Q00"
    exp.quantum_system.get_qubit.return_value = SimpleNamespace(
        control_frequency_fh_value=configured_fh_frequency
    )
    exp.ctx.resolve_ge_label.return_value = "Q00_ge"
    exp.ctx.resolve_ef_label.return_value = "Q00-ef"
    exp.ctx.resolve_fh_label.return_value = "Q00-fh"
    exp.ctx.resolve_read_label.return_value = "Q00_read"
    exp.targets = {
        "Q00_ge": object(),
        "Q00-ef": object(),
        "Q00-fh": object(),
    }
    exp.modified_frequencies.return_value = nullcontext()
    return exp


def test_run_passes_fh_seed_sweeps_and_qubex_default_amplitude(monkeypatch) -> None:
    task = _task()
    exp = _experiment()
    monkeypatch.setattr(task, "get_experiment", lambda backend: exp)
    estimate = create_autospec(
        estimate_fh_frequency_from_chevron_adaptive, return_value=_result().raw_result
    )
    with patch(
        "qdash.workflow.calibtasks.qubex.one_qubit_fine.check_adaptive_fh_chevron."
        "estimate_fh_frequency_from_chevron_adaptive",
        estimate,
    ):
        result = task.run(cast("Any", object()), "0")

    kwargs = estimate.call_args.kwargs
    assert kwargs["targets"] == ["Q00"]
    assert kwargs["frequencies"] == {"Q00": pytest.approx(4.44)}
    assert kwargs["amplitudes"] == {"Q00": pytest.approx(0.12 / np.sqrt(3))}
    np.testing.assert_allclose(kwargs["final_detuning_range"], np.linspace(-0.05, 0.05, 41))
    assert list(kwargs["final_time_range"]) == list(range(0, 257, 8))
    assert kwargs["n_shots"] == 256
    assert kwargs["shot_interval"] == task.run_parameters["interval"].get_value()
    assert kwargs["plot"] is False and kwargs["save_image"] is False
    assert result.raw_result is estimate.return_value
    exp.params.control_amplitude.__setitem__.assert_called_once_with("Q00", 0.12)
    exp.params.readout_amplitude.__setitem__.assert_called_once_with("Q00", 0.031)
    exp.modified_frequencies.assert_called_once_with(
        {"Q00_ge": 5.001, "Q00-ef": 4.72, "Q00_read": 6.1}
    )


def test_run_derives_fh_seed_from_ge_and_ef_when_fh_frequency_is_unset(monkeypatch) -> None:
    task = _task()
    exp = _experiment(configured_fh_frequency=None)
    monkeypatch.setattr(task, "get_experiment", lambda backend: exp)
    estimate = create_autospec(
        estimate_fh_frequency_from_chevron_adaptive, return_value=_result().raw_result
    )
    with patch(
        "qdash.workflow.calibtasks.qubex.one_qubit_fine.check_adaptive_fh_chevron."
        "estimate_fh_frequency_from_chevron_adaptive",
        estimate,
    ):
        task.run(cast("Any", object()), "0")

    assert estimate.call_args.kwargs["frequencies"]["Q00"] == pytest.approx(2 * 4.72 - 5.001)


def test_run_rejects_missing_fh_target_before_measurement() -> None:
    exp = _experiment()
    del exp.targets["Q00-fh"]
    backend = SimpleNamespace(get_instance=lambda: exp)
    with (
        patch(
            "qdash.workflow.calibtasks.qubex.one_qubit_fine.check_adaptive_fh_chevron."
            "estimate_fh_frequency_from_chevron_adaptive"
        ) as estimate,
        pytest.raises(ValueError, match="configuration_mode='ge-ef-fh'"),
    ):
        _task().run(cast("Any", backend), "0")
    estimate.assert_not_called()
    exp.modified_frequencies.assert_not_called()


def test_postprocess_uses_final_frequency_and_prioritizes_final_chevron_figure() -> None:
    figures = {
        "Q00-fh_search_measurement": go.Figure(),
        "Q00-fh_search_transform": go.Figure(),
        "Q00-fh_measurement": go.Figure(),
        "Q00-fh_transform": go.Figure(),
    }
    result = _task().postprocess(_backend(), "exec-1", _result(figures=figures), "0")
    assert result.validation_error is None
    assert result.output_parameters["fh_frequency"].value == 4.44
    assert result.output_parameters["fh_frequency"].execution_id == "exec-1"
    expected_keys = [
        "Q00-fh_measurement",
        "Q00-fh_transform",
        "Q00-fh_search_measurement",
        "Q00-fh_search_transform",
    ]
    assert len(result.figures) == len(expected_keys)
    assert all(
        figure is figures[key] for figure, key in zip(result.figures, expected_keys, strict=True)
    )


@pytest.mark.parametrize(
    "frequency,ratio",
    [(None, 8.5), (np.nan, 8.5), (np.inf, 8.5), (4.8, 8.5), (4.44, None), (4.44, 4.99)],
)
def test_postprocess_rejects_invalid_measurements(frequency, ratio) -> None:
    result = _task().postprocess(_backend(), "exec-1", _result(frequency, ratio), "0")
    assert result.validation_error is not None


def test_registered_task_saves_fh_frequency_and_control_frequency_fh() -> None:
    task = generate_task_instances(
        ["CheckAdaptiveFHChevron"], {"CheckAdaptiveFHChevron": {}}, "qubex"
    )["CheckAdaptiveFHChevron"]
    task.input_parameters["control_frequency_ef"] = InputParameterModel(value=4.72)
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
    assert saved["output_parameters"]["fh_frequency"]["value"] == 4.44
    assert saved["output_parameters"]["control_frequency_fh"]["value"] == 4.44
    metric = load_metrics_config().qubit_metrics["fh_frequency"]
    assert metric.unit == "GHz" and metric.scale == 1
    assert resolve_param_yaml_file_names({"control_frequency_fh": {"value": 4.44}}) == {
        "control_frequency_fh.yaml"
    }


def test_legacy_task_name_is_not_registered() -> None:
    with pytest.raises(ValueError, match="CheckFHChevron"):
        generate_task_instances(["CheckFHChevron"], {"CheckFHChevron": {}}, "qubex")
