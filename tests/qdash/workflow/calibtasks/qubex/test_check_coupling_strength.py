"""Tests for coupling strength measurement and persistence."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import plotly.graph_objects as go
import pytest

from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.qubex.two_qubit.check_coupling_strength import CheckCouplingStrength
from qdash.workflow.engine.task.backend_saver import BackendSaver


def _set_measurement_inputs(
    task: CheckCouplingStrength,
    *,
    control_qubit_anharmonicity: float | None = -0.3,
    target_qubit_anharmonicity: float | None = -0.31,
) -> None:
    values = {
        "control_qubit_frequency": 5.0,
        "control_qubit_anharmonicity": control_qubit_anharmonicity,
        "control_readout_frequency": 7.0,
        "control_readout_amplitude": 0.1,
        "target_qubit_frequency": 5.2,
        "target_qubit_anharmonicity": target_qubit_anharmonicity,
        "target_readout_frequency": 7.2,
        "target_readout_amplitude": 0.2,
    }
    for name, value in values.items():
        task.input_parameters[name].value = value


@pytest.fixture
def task_and_experiment(monkeypatch):
    task = CheckCouplingStrength()
    exp = MagicMock()
    exp.get_qubit_label.side_effect = lambda qid: f"Q{qid:02d}"
    exp.get_resonator_label.side_effect = lambda qid: f"R{qid:02d}"
    exp.params.readout_amplitude = {}
    pulses = {"Q00": MagicMock(), "Q01": MagicMock()}
    exp.hpi_pulse = pulses
    _set_measurement_inputs(task)
    monkeypatch.setattr(task, "get_experiment", lambda backend: exp)
    return task, exp


def test_run_passes_pulses_sweep_and_returns_r2(task_and_experiment) -> None:
    task, exp = task_and_experiment
    pulses = exp.hpi_pulse
    raw = SimpleNamespace(data={"zeta": -0.00002, "r2": 0.96})
    exp.jazz_experiment.return_value = raw
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
    exp.modified_frequencies.assert_called_once_with(
        {"Q00": 5.0, "Q01": 5.2, "R00": 7.0, "R01": 7.2}
    )
    assert exp.params.readout_amplitude == {"Q00": 0.1, "Q01": 0.2}
    assert raw.data == {"zeta": -0.00002, "r2": 0.96}


@pytest.mark.parametrize(
    ("control_qubit_anharmonicity", "target_qubit_anharmonicity"),
    [(None, -0.31), (-0.3, None), (None, None)],
)
def test_postprocess_omits_strength_when_either_anharmonicity_is_missing(
    task_and_experiment,
    control_qubit_anharmonicity: float | None,
    target_qubit_anharmonicity: float | None,
) -> None:
    task, _ = task_and_experiment
    _set_measurement_inputs(
        task,
        control_qubit_anharmonicity=control_qubit_anharmonicity,
        target_qubit_anharmonicity=target_qubit_anharmonicity,
    )
    result = task.postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"g": 123.0, "zeta": -0.00002})),
        "0-1",
    )

    assert set(result.output_parameters) == {"static_zz_interaction"}


def test_postprocess_omits_strength_output_when_not_calculated() -> None:
    result = CheckCouplingStrength().postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"zeta": -0.00002})),
        "0-1",
    )

    assert set(result.output_parameters) == {"static_zz_interaction"}
    assert result.validation_error is None


@pytest.mark.parametrize("zeta", [-0.00002, 0.0])
def test_postprocess_calculates_coupling_strength_in_mhz(zeta: float) -> None:
    task = CheckCouplingStrength()
    _set_measurement_inputs(task)
    figure = go.Figure()
    result = task.postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"zeta": zeta, "fig": figure})),
        "0-1",
    )

    expected = task._calculate_coupling_strength(
        xi=zeta / 2,
        control_frequency=5.0,
        target_frequency=5.2,
        control_qubit_anharmonicity=-0.3,
        target_qubit_anharmonicity=-0.31,
    )
    metric = result.output_parameters["qubit_qubit_coupling_strength"]
    assert metric.value == pytest.approx(expected * 1e3)
    assert metric.unit == "MHz"
    assert metric.qid_role == "coupling"
    assert metric.execution_id == "exec-1"
    assert result.figures == [figure]
    assert result.validation_error is None


def test_registered_task_saves_both_coupling_metrics() -> None:
    task = cast(
        "CheckCouplingStrength",
        generate_task_instances(["CheckCouplingStrength"], {"CheckCouplingStrength": {}}, "qubex")[
            "CheckCouplingStrength"
        ],
    )
    _set_measurement_inputs(task)
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
    expected = task._calculate_coupling_strength(
        xi=-0.00001,
        control_frequency=5.0,
        target_frequency=5.2,
        control_qubit_anharmonicity=-0.3,
        target_qubit_anharmonicity=-0.31,
    )
    assert saved["output_parameters"]["qubit_qubit_coupling_strength"].value == pytest.approx(
        expected * 1e3
    )
    assert saved["output_parameters"]["qubit_qubit_coupling_strength"].unit == "MHz"

    assert saved["output_parameters"]["static_zz_interaction"].value == pytest.approx(-20.0)
    assert saved["output_parameters"]["static_zz_interaction"].unit == "KHz"


def test_registered_task_saves_only_static_zz_without_anharmonicities() -> None:
    task = generate_task_instances(
        ["CheckCouplingStrength"], {"CheckCouplingStrength": {}}, "qubex"
    )["CheckCouplingStrength"]
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
        repository.return_value.get_calibration_data_for_update.return_value = {
            "qubit_qubit_coupling_strength": {"value": 4.5, "unit": "MHz"}
        }
        saver.save(task, cast("Any", execution), "0-1", backend, success=True)

    saved = repository.return_value.update_calib_data.call_args.kwargs
    assert set(saved["output_parameters"]) == {"static_zz_interaction"}


@pytest.mark.parametrize("zeta", [0.00002, -0.00002, 0.0])
def test_postprocess_converts_signed_static_zz_to_khz(zeta) -> None:
    result = CheckCouplingStrength().postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"zeta": zeta})),
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
        RunResult(raw_result=SimpleNamespace(data={"zeta": zeta})),
        "0-1",
    )
    assert result.validation_error is not None
    assert "static_zz_interaction" in result.validation_error


def test_postprocess_clears_previous_strength_when_task_instance_is_reused() -> None:
    task = CheckCouplingStrength()
    _set_measurement_inputs(task)
    first = task.postprocess(
        cast("Any", object()),
        "exec-1",
        RunResult(raw_result=SimpleNamespace(data={"zeta": -0.00002})),
        "0-1",
    )
    task.input_parameters["target_qubit_anharmonicity"].value = None
    second = task.postprocess(
        cast("Any", object()),
        "exec-2",
        RunResult(raw_result=SimpleNamespace(data={"zeta": -0.00003})),
        "0-2",
    )

    assert "qubit_qubit_coupling_strength" in first.output_parameters
    assert set(second.output_parameters) == {"static_zz_interaction"}
    assert task.output_parameters["qubit_qubit_coupling_strength"].value is None
