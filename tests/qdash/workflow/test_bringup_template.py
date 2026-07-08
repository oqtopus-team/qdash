from __future__ import annotations

import importlib
from typing import Any

bringup_module = importlib.import_module("qdash.workflow.templates.bringup")
experimental_bringup_module = importlib.import_module(
    "qdash.workflow.templates.experimental_simultaneous_bringup"
)


class FakeCalibService:
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        FakeCalibService.last_kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps}


def test_bringup_injects_resonator_assignment_pattern(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    bringup_module.bringup(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
        resonator_assignment_pattern="16q",
    )

    assert FakeCalibService.last_kwargs is not None
    assert FakeCalibService.last_kwargs["default_run_parameters"] == {
        "interval": {"value": 150 * 1024, "value_type": "int"},
        "CheckResonatorSpectroscopy": {
            "resonator_assignment_pattern": {"value": "16q", "value_type": "str"}
        },
    }


def test_bringup_starts_with_configure_all(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    result = bringup_module.bringup(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
    )

    assert [step.name for step in result["steps"]] == ["configure_all", "bringup"]


def test_bringup_step_accepts_resonator_assignment_pattern() -> None:
    from qdash.workflow.service.steps import BringUp

    service = type(
        "Service",
        (),
        {"default_run_parameters": {"interval": {"value": 1, "value_type": "int"}}},
    )()
    step = BringUp(mode="scheduled", resonator_assignment_pattern="16q")

    step._apply_resonator_assignment_pattern(service)

    assert service.default_run_parameters == {
        "interval": {"value": 1, "value_type": "int"},
        "CheckResonatorSpectroscopy": {
            "resonator_assignment_pattern": {"value": "16q", "value_type": "str"}
        },
    }


def test_experimental_simultaneous_bringup_defaults_to_all_mode(monkeypatch) -> None:
    monkeypatch.setattr(experimental_bringup_module, "CalibService", FakeCalibService)

    result = experimental_bringup_module.experimental_simultaneous_bringup(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
    )

    step = result["steps"][0]
    assert step.simultaneous_spectroscopy_schedule_mode == "all"


def test_bringup_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    result = bringup_module.bringup(username="alice", chip_id="16Q-test", mux_ids=[0])

    assert result["steps"][1].tasks == bringup_module.BRINGUP_TASKS


def test_experimental_simultaneous_bringup_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(experimental_bringup_module, "CalibService", FakeCalibService)

    result = experimental_bringup_module.experimental_simultaneous_bringup(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
    )

    assert result["steps"][0].tasks == (
        experimental_bringup_module.EXPERIMENTAL_SIMULTANEOUS_BRINGUP_TASKS
    )
