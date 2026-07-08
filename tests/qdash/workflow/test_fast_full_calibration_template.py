from __future__ import annotations

import importlib
from typing import Any

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
    assert one_qubit_check.tasks == ["CheckRabi", "CreateHPIPulse", "CheckHPIPulse"]

    one_qubit_fine_tune = steps[3]
    assert "X90InterleavedRandomizedBenchmarking" in one_qubit_fine_tune.tasks
    assert "CheckT1Average" not in one_qubit_fine_tune.tasks
    assert "CheckT2EchoAverage" not in one_qubit_fine_tune.tasks
    assert "Check1QGateCoherenceLimit" not in one_qubit_fine_tune.tasks
