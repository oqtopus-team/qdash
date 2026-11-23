from __future__ import annotations

import importlib
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.workflow.service.steps import (
    ConfigureAll,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
    Pipeline,
    StepContext,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import MuxTargets
from tests.qdash.workflow.task_call_helpers import names, settings

fast_full_module = importlib.import_module("qdash.workflow.templates.fast_full_calibration")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "service_kwargs": self.kwargs}


def test_fast_full_calibration_uses_shortened_one_qubit_steps(monkeypatch) -> None:
    monkeypatch.setattr(fast_full_module, "CalibService", FakeCalibService)

    result = fast_full_module.fast_full_calibration(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0]

    steps = result["steps"]
    assert [type(step) for step in steps] == [
        ConfigureAll,
        OneQubitCheck,
        FilterByStatus,
        ConfigureAll,
        OneQubitFineTune,
        FilterByMetric,
        GenerateCRSchedule,
        TwoQubitCalibration,
    ]

    one_qubit_check = steps[1]
    assert names(one_qubit_check.tasks) == [
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CheckRamsey",
    ]
    assert "CheckT1" not in names(one_qubit_check.tasks)
    assert "CheckT2Echo" not in names(one_qubit_check.tasks)

    one_qubit_fine_tune = steps[4]
    assert "X90InterleavedRandomizedBenchmarking" in names(one_qubit_fine_tune.tasks)
    assert "CheckT1Average" not in names(one_qubit_fine_tune.tasks)
    assert "CheckT2EchoAverage" not in names(one_qubit_fine_tune.tasks)
    assert "Check1QGateCoherenceLimit" not in names(one_qubit_fine_tune.tasks)

    # The fast template keeps its explicit order while omitting the expensive coherence task.
    assert names(steps[7].tasks) == names(fast_full_module.FAST_2Q_TASKS)
    assert "Check2QGateCoherenceLimit" not in names(steps[7].tasks)


def test_fast_full_calibration_reconfigures_before_fine_tune(monkeypatch) -> None:
    monkeypatch.setattr(fast_full_module, "CalibService", FakeCalibService)

    steps = fast_full_module.fast_full_calibration(username="alice", chip_id="64Q", mux_ids=[0, 1])[
        "steps"
    ]

    # The repeated ConfigureAll needs its own step_id for the plan to validate.
    Pipeline(steps)
    configure_steps = [step for step in steps if isinstance(step, ConfigureAll)]
    assert [step.resolved_step_id for step in configure_steps] == [
        "configure_all",
        "configure_all_before_fine_tune",
    ]
    second = steps.index(configure_steps[1])
    assert isinstance(steps[second - 1], FilterByStatus)
    assert isinstance(steps[second + 1], OneQubitFineTune)


def test_fast_full_calibration_second_configure_keeps_filtered_candidates(monkeypatch) -> None:
    monkeypatch.setattr(fast_full_module, "CalibService", FakeCalibService)
    monkeypatch.setattr("qdash.workflow.service.steps.box_setup.get_run_logger", MagicMock)

    result = fast_full_module.fast_full_calibration(username="alice", chip_id="64Q", mux_ids=[0, 1])
    second_configure = result["steps"][3]
    session = MagicMock()
    session.plan_digest = None
    ctx = StepContext(candidate_qids=["0", "5"])

    ctx = second_configure.execute(session, result["targets"], ctx)

    # Every selected MUX is reconfigured, but only the filtered qubits move on.
    _, kwargs = session.execute_task.call_args
    assert kwargs["parameters"]["run"]["mux_ids"] == {"value": [0, 1]}
    assert kwargs["invocation"].step_id == "configure_all_before_fine_tune"
    assert ctx.candidate_qids == ["0", "5"]


def test_fast_full_calibration_requires_explicit_mux_ids(monkeypatch) -> None:
    monkeypatch.setattr(fast_full_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids is required"):
        fast_full_module.fast_full_calibration(username="alice", chip_id="64Q")


PULSE_DURATIONS = {
    "CreateHPIPulse": {"hpi_duration": 32},
    "CreatePIPulse": {"pi_duration": 32},
    "CreateDRAGHPIPulse": {"drag_hpi_duration": 16},
    "CreateDRAGPIPulse": {"drag_pi_duration": 24},
}


def test_fast_full_calibration_sets_durations_on_every_pulse_call(monkeypatch) -> None:
    monkeypatch.setattr(fast_full_module, "CalibService", FakeCalibService)

    result = fast_full_module.fast_full_calibration(username="alice", chip_id="64Q", mux_ids=[0])

    assert "task_parameters" not in result["service_kwargs"]
    assert result["service_kwargs"]["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": 150 * 1024,
    }
    pulse_calls = []
    for step in result["steps"]:
        for call in getattr(step, "tasks", None) or ():
            # Only pulse creation carries settings; the CR search uses task defaults.
            expected = settings(run=PULSE_DURATIONS.get(call.name, {}))
            assert call.effective_settings({}) == expected, call.resolved_call_id
            if call.name in PULSE_DURATIONS:
                pulse_calls.append(call.resolved_call_id)
    assert pulse_calls == [
        "CreateHPIPulse",
        "CreateHPIPulse",
        "CreatePIPulse",
        "CreateDRAGHPIPulse",
        "CreateDRAGPIPulse",
    ]
