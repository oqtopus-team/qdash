from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service.steps import CustomTwoQubit, TwoQubitCalibration
from tests.qdash.workflow.task_call_helpers import names, settings

two_qubit_module = importlib.import_module("qdash.workflow.templates.two_qubit")
two_qubit_pairs_module = importlib.import_module("qdash.workflow.templates.two_qubit_pairs")
two_qubit_manual_module = importlib.import_module(
    "qdash.workflow.templates.two_qubit_manual_rounds"
)


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


def test_two_qubit_pairs_template_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_pairs_module, "CalibService", FakeCalibService)

    result = two_qubit_pairs_module.two_qubit_pairs(
        username="alice",
        chip_id="64Q",
        coupling_pairs=[("0", "1")],
    )

    [step] = result["steps"]
    assert isinstance(step, TwoQubitCalibration)
    assert step.execution_mode == "automatic" and step.max_parallel_ops == 10
    assert names(step.tasks) == names(two_qubit_pairs_module.TWO_QUBIT_PAIRS_TASKS)
    assert step.tasks is not None
    assert all(call.effective_settings({}) == settings() for call in step.tasks)
    assert "task_parameters" not in result["kwargs"]


def test_two_qubit_pairs_template_keeps_custom_tasks(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_pairs_module, "CalibService", FakeCalibService)

    result = two_qubit_pairs_module.two_qubit_pairs(
        username="alice",
        chip_id="64Q",
        coupling_pairs=[("0", "1")],
        tasks=[TaskCall(name="CheckCrossResonance")],
        max_parallel_ops=3,
    )

    [step] = result["steps"]
    assert isinstance(step, CustomTwoQubit) and step.max_parallel_ops == 3
    assert names(step.tasks) == ["CheckCrossResonance"]


def test_two_qubit_pairs_template_targets_exactly_the_directed_pairs(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_pairs_module, "CalibService", FakeCalibService)

    result = two_qubit_pairs_module.two_qubit_pairs(
        "alice", "64Q", [("0", "1"), ("1", "0")], None, 10, ["daily"], "custom_flow", "project-1"
    )

    assert result["targets"].to_coupling_ids("64Q") == ["0-1", "1-0"]
    assert result["kwargs"]["tags"] == ["daily"]
    assert result["kwargs"]["flow_name"] == "custom_flow"
    assert result["kwargs"]["project_id"] == "project-1"


def test_two_qubit_pairs_template_accepts_a_pair_override(monkeypatch) -> None:
    """A pair override replaces the targets; the step stays and groups those pairs."""
    from qdash.datamodel.flow_targets import FlowTargetOverride
    from qdash.workflow.service.flow_targets import override_pipeline

    monkeypatch.setattr(two_qubit_pairs_module, "CalibService", FakeCalibService)
    result = two_qubit_pairs_module.two_qubit_pairs(
        username="alice", chip_id="64Q", coupling_pairs=[("0", "1"), ("4", "5")]
    )
    override = FlowTargetOverride(coupling_pairs=[["63", "85"], ["85", "63"]])

    targets, steps = override_pipeline(result["targets"], result["steps"], override)

    assert targets.to_coupling_ids("64Q") == ["63-85", "85-63"]
    assert steps == result["steps"]


@pytest.mark.parametrize(
    ("pairs", "message"),
    [
        (None, "Specify coupling_pairs"),
        ([], "Specify coupling_pairs"),
        ([("0", "0")], "Invalid pair"),
        ([("0", "1", "2")], "Invalid pair"),
        ([("0", "1"), ("0", "1")], "duplicates"),
    ],
)
def test_two_qubit_pairs_template_validates_pairs(monkeypatch, pairs, message) -> None:
    monkeypatch.setattr(two_qubit_pairs_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match=message):
        two_qubit_pairs_module.two_qubit_pairs(
            username="alice", chip_id="64Q", coupling_pairs=pairs
        )


def test_two_qubit_manual_rounds_template_runs_its_rounds(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_manual_module, "CalibService", FakeCalibService)

    result = two_qubit_manual_module.two_qubit_manual_rounds(username="alice", chip_id="64Q")

    [step] = result["steps"]
    assert isinstance(step, TwoQubitCalibration)
    assert step.execution_mode == "manual"
    assert step.rounds == two_qubit_manual_module.ROUNDS
    assert names(step.tasks) == names(two_qubit_manual_module.TWO_QUBIT_MANUAL_ROUNDS_TASKS)
    assert step.rounds is not None
    pairs = [pair for round_ in step.rounds for pair in round_]
    assert result["targets"].pairs == pairs == two_qubit_manual_module.TARGET_PAIRS


def test_two_qubit_manual_rounds_template_keeps_custom_tasks(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_manual_module, "CalibService", FakeCalibService)

    result = two_qubit_manual_module.two_qubit_manual_rounds(
        username="alice", chip_id="64Q", tasks=[TaskCall(name="CheckCrossResonance")]
    )

    [step] = result["steps"]
    assert isinstance(step, CustomTwoQubit) and step.execution_mode == "manual"
    assert step.rounds == two_qubit_manual_module.ROUNDS
    assert names(step.tasks) == ["CheckCrossResonance"]


def test_two_qubit_manual_rounds_template_rejects_target_overrides(monkeypatch) -> None:
    from qdash.datamodel.flow_targets import FlowTargetOverride
    from qdash.workflow.service.flow_targets import override_pipeline

    monkeypatch.setattr(two_qubit_manual_module, "CalibService", FakeCalibService)
    result = two_qubit_manual_module.two_qubit_manual_rounds(username="alice", chip_id="64Q")

    with pytest.raises(ValueError, match="Target overrides are not accepted"):
        override_pipeline(
            result["targets"],
            result["steps"],
            FlowTargetOverride(coupling_pairs=[["0", "1"]]),
        )


def test_two_qubit_manual_rounds_template_requires_matching_targets(monkeypatch) -> None:
    monkeypatch.setattr(two_qubit_manual_module, "CalibService", FakeCalibService)
    monkeypatch.setattr(two_qubit_manual_module, "TARGET_PAIRS", [("0", "1")])

    with pytest.raises(ValueError, match="TARGET_PAIRS must list every pair of ROUNDS"):
        two_qubit_manual_module.two_qubit_manual_rounds(username="alice", chip_id="64Q")


def test_catalog_separates_automatic_pairs_and_manual_rounds():
    import json
    from pathlib import Path

    assert two_qubit_module.__file__ is not None
    catalog = json.loads(Path(two_qubit_module.__file__).with_name("templates.json").read_text())
    entries = {entry["id"]: entry for entry in catalog}
    assert entries["two_qubit_pairs"]["name"] == "2Q Automatic Pairs"
    assert entries["two_qubit_manual_rounds"]["name"] == "2Q Manual Rounds"
    assert "two_qubit_scheduled" not in entries
    for key in ("two_qubit_pairs", "two_qubit_manual_rounds"):
        assert entries[key]["function_name"] == key
        assert Path(two_qubit_module.__file__).with_name(entries[key]["filename"]).is_file()
