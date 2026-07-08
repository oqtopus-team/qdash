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
    assert steps[1].tasks == full_module.FULL_1Q_CHECK_TASKS
    assert steps[3].tasks == full_module.FULL_1Q_FINE_TUNE_TASKS
    assert steps[6].tasks == full_module.FULL_2Q_TASKS


def test_full_calibration_requires_explicit_mux_ids(monkeypatch) -> None:
    monkeypatch.setattr(full_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids is required"):
        full_module.full_calibration(username="alice", chip_id="64Q")
