from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.service.steps import (
    ConfigureAll,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
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
        OneQubitFineTune,
        FilterByMetric,
        GenerateCRSchedule,
        TwoQubitCalibration,
    ]

    one_qubit_check = steps[1]
    assert names(one_qubit_check.tasks) == ["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"]

    one_qubit_fine_tune = steps[3]
    assert "X90InterleavedRandomizedBenchmarking" in names(one_qubit_fine_tune.tasks)
    assert "CheckT1Average" not in names(one_qubit_fine_tune.tasks)
    assert "CheckT2EchoAverage" not in names(one_qubit_fine_tune.tasks)
    assert "Check1QGateCoherenceLimit" not in names(one_qubit_fine_tune.tasks)

    # The fast template keeps its explicit order while omitting the expensive coherence task.
    assert names(steps[6].tasks) == names(fast_full_module.FAST_2Q_TASKS)
    assert "Check2QGateCoherenceLimit" not in names(steps[6].tasks)


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
