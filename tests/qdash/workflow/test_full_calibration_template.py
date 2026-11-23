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
from tests.qdash.workflow.task_call_helpers import names, settings

full_module = importlib.import_module("qdash.workflow.templates.full_calibration")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "service_kwargs": self.kwargs}


def test_full_calibration_passes_template_task_lists(monkeypatch) -> None:
    monkeypatch.setattr(full_module, "CalibService", FakeCalibService)

    result = full_module.full_calibration(username="alice", chip_id="64Q", mux_ids=[0])

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
    assert names(steps[1].tasks) == names(full_module.FULL_1Q_CHECK_TASKS)
    assert names(steps[3].tasks) == names(full_module.FULL_1Q_FINE_TUNE_TASKS)
    assert names(steps[6].tasks) == names(full_module.FULL_2Q_TASKS)


def test_full_calibration_requires_explicit_mux_ids(monkeypatch) -> None:
    monkeypatch.setattr(full_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids is required"):
        full_module.full_calibration(username="alice", chip_id="64Q")


PULSE_DURATIONS = {
    "CreateHPIPulse": {"hpi_duration": 32},
    "CreatePIPulse": {"pi_duration": 32},
    "CreateDRAGHPIPulse": {"drag_hpi_duration": 16},
    "CreateDRAGPIPulse": {"drag_pi_duration": 24},
}


def test_full_calibration_sets_durations_on_every_pulse_call(monkeypatch) -> None:
    monkeypatch.setattr(full_module, "CalibService", FakeCalibService)

    result = full_module.full_calibration(username="alice", chip_id="64Q", mux_ids=[0])

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
        "hpi_create_first",
        "hpi_create_second",
        "CreateHPIPulse",
        "CreatePIPulse",
        "CreateDRAGHPIPulse",
        "CreateDRAGPIPulse",
    ]
