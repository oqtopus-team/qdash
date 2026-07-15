from __future__ import annotations

import importlib
from typing import Any

two_qubit_module = importlib.import_module("qdash.workflow.templates.two_qubit")
two_qubit_scheduled_module = importlib.import_module("qdash.workflow.templates.two_qubit_scheduled")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps}


def test_two_qubit_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_module, "CalibService", FakeCalibService)

    result = two_qubit_module.two_qubit(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    assert result["steps"][1].tasks == two_qubit_module.TWO_QUBIT_TASKS


def test_two_qubit_template_keeps_custom_tasks(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_module, "CalibService", FakeCalibService)

    result = two_qubit_module.two_qubit(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
        tasks=["CheckCrossResonance"],
    )

    assert result["steps"][1].tasks == ["CheckCrossResonance"]


def test_two_qubit_scheduled_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)

    result = two_qubit_scheduled_module.two_qubit_scheduled(
        username="alice",
        chip_id="64Q",
        schedule=[[("0", "1")]],
    )

    assert result["steps"][1].tasks == two_qubit_scheduled_module.TWO_QUBIT_SCHEDULED_TASKS


def test_two_qubit_scheduled_template_keeps_custom_tasks(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)

    result = two_qubit_scheduled_module.two_qubit_scheduled(
        username="alice",
        chip_id="64Q",
        schedule=[[("0", "1")]],
        tasks=["CheckCrossResonance"],
    )

    assert result["steps"][1].tasks == ["CheckCrossResonance"]
