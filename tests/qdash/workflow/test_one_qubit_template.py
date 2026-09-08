from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.service.targets import MuxTargets, QubitTargets

one_qubit_module = importlib.import_module("qdash.workflow.templates.one_qubit")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "kwargs": self.kwargs}


def test_one_qubit_template_uses_explicit_qids(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    assert isinstance(result["targets"], QubitTargets)
    assert result["targets"].qids == ["0", "1"]


def test_one_qubit_template_prefers_mux_ids(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
        qids=["8"],
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0]


def test_one_qubit_template_requires_explicit_targets(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        one_qubit_module.one_qubit(username="alice", chip_id="64Q")


def test_one_qubit_template_passes_template_task_lists(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(username="alice", chip_id="64Q", mux_ids=[0])

    steps = result["steps"]
    assert steps[0].tasks == one_qubit_module.ONE_QUBIT_CHECK_TASKS
    assert steps[2].tasks == one_qubit_module.ONE_QUBIT_FINE_TUNE_TASKS


def test_one_qubit_template_check_only_passes_template_task_list(monkeypatch) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(
        username="alice", chip_id="64Q", mux_ids=[0], check_only=True
    )

    assert result["steps"][0].tasks == one_qubit_module.ONE_QUBIT_CHECK_TASKS


@pytest.mark.parametrize("use_mux", [False, True])
def test_fine_one_runs_only_configure_and_existing_fine_tune_stage(monkeypatch, use_mux) -> None:
    from qdash.workflow.service.steps import OneQubitFineTune

    fine_one_module = importlib.import_module("qdash.workflow.templates.fine_one")
    monkeypatch.setattr(fine_one_module, "CalibService", FakeCalibService)
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)
    result = fine_one_module.fine_one(
        username="alice",
        chip_id="64Q",
        qids=["8"],
        mux_ids=[0] if use_mux else None,
        exclude_qids=["2"],
        flow_name="fine-check",
        tags=["fine"],
        project_id="project-1",
    )

    if use_mux:
        assert isinstance(result["targets"], MuxTargets)
        assert result["targets"].mux_ids == [0]
        assert result["targets"].exclude_qids == ["2"]
    else:
        assert isinstance(result["targets"], QubitTargets)
        assert result["targets"].qids == ["8"]
    assert len(result["steps"]) == 1
    step = result["steps"][0]
    assert isinstance(step, OneQubitFineTune)
    assert step.mode == "synchronized"
    assert step.tasks == ["Configure", *one_qubit_module.ONE_QUBIT_FINE_TUNE_TASKS]
    full = one_qubit_module.one_qubit(username="alice", chip_id="64Q", qids=["8"])
    assert result["kwargs"]["default_run_parameters"] == full["kwargs"]["default_run_parameters"]
    assert result["kwargs"]["flow_name"] == "fine-check"
    assert result["kwargs"]["project_id"] == "project-1"
    assert result["kwargs"]["tags"] == ["fine"]
    assert "skip_execution" not in result["kwargs"]


def test_fine_one_requires_explicit_targets(monkeypatch) -> None:
    fine_one_module = importlib.import_module("qdash.workflow.templates.fine_one")
    monkeypatch.setattr(fine_one_module, "CalibService", FakeCalibService)
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        fine_one_module.fine_one(username="alice", chip_id="64Q")
