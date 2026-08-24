from __future__ import annotations

import importlib
from typing import Any

import pytest

bringup_module = importlib.import_module("qdash.workflow.templates.bringup")


class FakeCalibService:
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        FakeCalibService.last_kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps}


def test_bringup_starts_with_configure_all(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    result = bringup_module.bringup(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
    )

    assert [step.name for step in result["steps"]] == ["configure_all", "bringup"]


def test_bringup_step_accepts_resonator_assignment_order() -> None:
    from qdash.workflow.service.steps import BringUp

    service = type(
        "Service",
        (),
        {"default_run_parameters": {"interval": {"value": 1, "value_type": "int"}}},
    )()
    step = BringUp(mode="scheduled", resonator_assignment_order=[0, 3, 1, 2])

    step._apply_resonator_assignment_order(service)

    assert service.default_run_parameters == {
        "interval": {"value": 1, "value_type": "int"},
        "CheckResonatorSpectroscopy": {
            "resonator_assignment_order": {"value": [0, 3, 1, 2], "value_type": "list"}
        },
    }


def test_bringup_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    result = bringup_module.bringup(username="alice", chip_id="16Q-test", mux_ids=[0])

    assert result["steps"][1].tasks == bringup_module.BRINGUP_TASKS


def test_bringup_template_requires_explicit_mux_ids(monkeypatch) -> None:
    monkeypatch.setattr(bringup_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids is required"):
        bringup_module.bringup(username="alice", chip_id="16Q-test")
