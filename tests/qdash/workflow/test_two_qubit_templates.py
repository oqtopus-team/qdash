from __future__ import annotations

import importlib
from typing import Any

import pytest

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


def test_two_qubit_scheduled_template_preserves_positional_arguments(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)
    schedule = [[("0", "1")]]
    tasks = [TaskCall(name="CheckCrossResonance")]

    result = two_qubit_scheduled_module.two_qubit_scheduled(
        "alice", "64Q", schedule, tasks, ["daily"], "custom_flow", "project-1"
    )

    assert result["steps"][0].schedule == schedule
    assert names(result["steps"][1].tasks) == ["CheckCrossResonance"]
    assert result["kwargs"]["tags"] == ["daily"]
    assert result["kwargs"]["flow_name"] == "custom_flow"
    assert result["kwargs"]["project_id"] == "project-1"


def test_two_qubit_scheduled_template_runs_only_selected_pairs(monkeypatch) -> None:
    """A pair override replaces both the template's targets and its saved schedule."""
    from qdash.datamodel.flow_targets import FlowTargetOverride
    from qdash.workflow.service.flow_targets import override_pipeline
    from qdash.workflow.service.steps import SetCRSchedule

    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)
    result = two_qubit_scheduled_module.two_qubit_scheduled(
        username="alice",
        chip_id="64Q",
        schedule=[[("0", "1"), ("4", "5")], [("2", "3")]],
    )
    override = FlowTargetOverride(coupling_pairs=[["63", "85"], ["64", "42"], ["39", "61"]])

    targets, steps = override_pipeline(
        result["targets"],
        result["steps"],
        override,
        lambda pairs: [pairs[:2], pairs[2:]],
    )

    assert targets.to_coupling_ids("64Q") == ["63-85", "64-42", "39-61"]
    schedules = [step.schedule for step in steps if isinstance(step, SetCRSchedule)]
    assert schedules == [[[("63", "85"), ("64", "42")], [("39", "61")]]]
    assert steps[1] is result["steps"][1]


def test_two_qubit_scheduled_template_runs_coupling_pairs_one_per_group(monkeypatch) -> None:
    """Direct calls with pairs and no override never run two pairs at once."""
    from qdash.workflow.service.steps import SetCRSchedule

    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)
    result = two_qubit_scheduled_module.two_qubit_scheduled(
        username="alice",
        chip_id="64Q",
        schedule=[[("2", "3")]],
        coupling_pairs=[("0", "1"), ("1", "0")],
    )

    assert result["targets"].to_coupling_ids("64Q") == ["0-1", "1-0"]
    [schedule] = [step.schedule for step in result["steps"] if isinstance(step, SetCRSchedule)]
    assert schedule == [[("0", "1")], [("1", "0")]]


@pytest.mark.parametrize("kwargs", [{}, {"schedule": []}, {"coupling_pairs": []}])
def test_two_qubit_scheduled_template_requires_pairs(monkeypatch, kwargs) -> None:
    monkeypatch.setattr(two_qubit_scheduled_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match="Specify a non-empty schedule or coupling_pairs"):
        two_qubit_scheduled_module.two_qubit_scheduled(username="alice", chip_id="64Q", **kwargs)
