from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.calibtasks.qubex import CheckAdaptiveChevron
from tests.qdash.workflow.task_call_helpers import effective_settings, names, settings

bringup_module = importlib.import_module("qdash.workflow.templates.bringup")


class FakeCalibService:
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        FakeCalibService.last_kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps}


def test_bringup_starts_with_measurements(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    result = bringup_module.bringup(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
    )

    assert [step.name for step in result["steps"]] == ["bringup"]


def test_bringup_step_accepts_resonator_assignment_order() -> None:
    from qdash.datamodel.task_call import TaskCall
    from qdash.workflow.service.steps import BringUp

    step = BringUp(mode="scheduled", resonator_assignment_order=[0, 3, 1, 2])

    resonator = [call for call in step.calls() if call.name == "CheckResonatorSpectroscopy"]
    assert resonator
    assert all(
        call.settings()["run"]["resonator_assignment_order"] == {"value": [0, 3, 1, 2]}
        for call in resonator
    )
    assert all(
        "resonator_assignment_order" not in (call.run or {})
        for call in step.calls()
        if call.name != "CheckResonatorSpectroscopy"
    )
    # A call's own order takes precedence over the step's.
    own = BringUp(
        tasks=[
            TaskCall(name="CheckResonatorSpectroscopy", run={"resonator_assignment_order": [1]})
        ],
        resonator_assignment_order=[0, 3, 1, 2],
    )
    assert own.calls()[0].settings()["run"]["resonator_assignment_order"] == {"value": [1]}


def test_bringup_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    result = bringup_module.bringup(username="alice", chip_id="16Q-test", mux_ids=[0])

    assert names(result["steps"][0].tasks) == names(bringup_module.BRINGUP_TASKS)


def test_bringup_template_preserves_task_specific_acquisition_settings(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    result = bringup_module.bringup(username="alice", chip_id="16Q-test", mux_ids=[0])

    assert FakeCalibService.last_kwargs is not None
    assert "task_parameters" not in FakeCalibService.last_kwargs
    assert FakeCalibService.last_kwargs["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": 150 * 1024,
    }
    # Call settings take precedence over the shared interval default.
    assert effective_settings(result["steps"][0].tasks) == [
        ("CheckResonatorSpectroscopy", settings(run={"shots": 1024, "interval": 0})),
        ("CheckQubitSpectroscopy", settings(run={"shots": 1024, "interval": 1024})),
        ("CheckControlAmplitude", settings(run={"shots": 8192})),
        ("CheckAdaptiveChevron", settings(run={"shots": 256})),
    ]
    adaptive = result["steps"][0].tasks[-1]
    assert adaptive.run is not None
    assert adaptive.run["shots"]["value"] == CheckAdaptiveChevron.run_spec["shots"].default


def test_bringup_template_requires_explicit_mux_ids(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids is required"):
        bringup_module.bringup(username="alice", chip_id="16Q-test")
