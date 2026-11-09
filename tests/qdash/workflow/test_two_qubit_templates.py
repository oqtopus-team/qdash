from __future__ import annotations

import importlib
from typing import Any

from qdash.datamodel.task_call import TaskCall
from tests.qdash.workflow.task_call_helpers import names, settings

two_qubit_module = importlib.import_module("qdash.workflow.templates.two_qubit")
two_qubit_scheduled_module = importlib.import_module("qdash.workflow.templates.two_qubit_scheduled")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "kwargs": self.kwargs}


def test_two_qubit_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_module, "CalibService", FakeCalibService)

    result = two_qubit_module.two_qubit(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    assert names(result["steps"][1].tasks) == names(two_qubit_module.TWO_QUBIT_TASKS)
    # The CR search example is commented out, so every call uses the task defaults.
    assert all(call.effective_settings({}) == settings() for call in result["steps"][1].tasks)
    assert "task_parameters" not in result["kwargs"]


def test_two_qubit_template_keeps_custom_tasks(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_module, "CalibService", FakeCalibService)

    result = two_qubit_module.two_qubit(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
        tasks=[TaskCall(name="CheckCrossResonance")],
    )

    assert names(result["steps"][1].tasks) == ["CheckCrossResonance"]


def test_two_qubit_scheduled_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)

    result = two_qubit_scheduled_module.two_qubit_scheduled(
        username="alice",
        chip_id="64Q",
        schedule=[[("0", "1")]],
    )

    assert names(result["steps"][1].tasks) == names(
        two_qubit_scheduled_module.TWO_QUBIT_SCHEDULED_TASKS
    )
    assert all(call.effective_settings({}) == settings() for call in result["steps"][1].tasks)
    assert "task_parameters" not in result["kwargs"]


def test_two_qubit_scheduled_template_keeps_custom_tasks(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)

    result = two_qubit_scheduled_module.two_qubit_scheduled(
        username="alice",
        chip_id="64Q",
        schedule=[[("0", "1")]],
        tasks=[TaskCall(name="CheckCrossResonance")],
    )

    assert names(result["steps"][1].tasks) == ["CheckCrossResonance"]
