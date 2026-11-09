from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.service.targets import MuxTargets, QubitTargets
from tests.qdash.workflow.task_call_helpers import call_ids, effective_settings, names, settings

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
    from qdash.workflow.service.steps import FilterByStatus
    from qdash.workflow.templates.coarse_one import COARSE_ONE_TASKS
    from qdash.workflow.templates.fine_one import FINE_ONE_TASKS

    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(username="alice", chip_id="64Q", mux_ids=[0])

    steps = result["steps"]
    assert len(steps) == 3
    # The stages match coarse_one and fine_one call for call, settings included.
    assert effective_settings(steps[0].tasks) == effective_settings(COARSE_ONE_TASKS)
    assert isinstance(steps[1], FilterByStatus)
    assert effective_settings(steps[2].tasks) == effective_settings(FINE_ONE_TASKS)
    assert "task_parameters" not in result["kwargs"]


PULSE_DURATIONS = {
    "CreateHPIPulse": {"hpi_duration": 32},
    "CreatePIPulse": {"pi_duration": 32},
    "CreateDRAGHPIPulse": {"drag_hpi_duration": 16},
    "CreateDRAGPIPulse": {"drag_pi_duration": 24},
}


@pytest.mark.parametrize("check_only", [False, True])
def test_one_qubit_template_sets_durations_on_every_pulse_call(monkeypatch, check_only) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(
        username="alice", chip_id="64Q", mux_ids=[0], check_only=check_only
    )

    pulse_calls = 0
    for step in result["steps"]:
        for call in getattr(step, "tasks", None) or ():
            expected = settings(run=PULSE_DURATIONS.get(call.name, {}))
            assert call.effective_settings({}) == expected, call.resolved_call_id
            pulse_calls += call.name in PULSE_DURATIONS
    # Four pulse types in the coarse stage, plus three rounds of them in the fine stage.
    assert pulse_calls == (4 if check_only else 16)


@pytest.mark.parametrize("check_only", [False, True])
def test_one_qubit_template_check_calibrates_and_checks_all_pulses(monkeypatch, check_only) -> None:
    monkeypatch.setattr(one_qubit_module, "CalibService", FakeCalibService)

    result = one_qubit_module.one_qubit(
        username="alice", chip_id="64Q", mux_ids=[0], check_only=check_only
    )

    assert len(result["steps"]) == (1 if check_only else 3)
    assert names(result["steps"][0].tasks) == [
        "Configure",
        "CheckCoarseReadoutParams",
        "Configure",
        "CheckRabi",
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CreateDRAGHPIPulse",
        "CheckDRAGHPIPulse",
        "CreateDRAGPIPulse",
        "CheckDRAGPIPulse",
        "CheckT1",
        "CheckT2Echo",
        "CheckRamsey",
    ]


@pytest.mark.parametrize("use_mux", [False, True])
def test_fine_one_optimizes_readout_before_classification_in_fine_tune_stage(
    monkeypatch, use_mux
) -> None:
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
    assert step.tasks is not None
    tasks = names(step.tasks)
    # Every repeated pulse calibration is its own call, named after its round.
    assert len(set(call_ids(step.calls()))) == len(step.tasks)
    assert tasks[0] == "Configure"
    optimization_indices = [
        i for i, name in enumerate(tasks) if name.startswith("CheckOptimalReadout")
    ]
    assert [tasks[i] for i in optimization_indices] == [
        "CheckOptimalReadoutAmplitude",
        "CheckOptimalReadoutFrequency",
        "CheckOptimalReadoutAmplitude",
        "CheckOptimalReadoutFrequency",
    ]
    for amplitude_index, frequency_index in zip(
        optimization_indices[::2], optimization_indices[1::2], strict=True
    ):
        assert frequency_index == amplitude_index + 1
        assert tasks[frequency_index + 1] == "Configure"
        # Refresh the base pulses and both DRAG pulses, with checks, before each pair.
        assert tasks[amplitude_index - 9 : amplitude_index] == [
            "CheckRabi",
            "CreateHPIPulse",
            "CheckHPIPulse",
            "CreatePIPulse",
            "CheckPIPulse",
            "CreateDRAGHPIPulse",
            "CheckDRAGHPIPulse",
            "CreateDRAGPIPulse",
            "CheckDRAGPIPulse",
        ]
    # Finish with the full pulse calibration at the final readout settings.
    omitted_tasks = {"CheckT1Average", "CheckT2EchoAverage", "Check1QGateCoherenceLimit"}
    assert omitted_tasks.isdisjoint(tasks)
    assert tasks[optimization_indices[-1] + 2 :] == [
        "CheckRabi",
        "CreateHPIPulse",
        "CheckHPIPulse",
        "CreatePIPulse",
        "CheckPIPulse",
        "CreateDRAGHPIPulse",
        "CheckDRAGHPIPulse",
        "CreateDRAGPIPulse",
        "CheckDRAGPIPulse",
        "ReadoutClassification",
        "RandomizedBenchmarking",
        "X90InterleavedRandomizedBenchmarking",
    ]
    full = one_qubit_module.one_qubit(username="alice", chip_id="64Q", qids=["8"])
    assert result["kwargs"]["default_run_parameters"] == full["kwargs"]["default_run_parameters"]
    assert "task_parameters" not in result["kwargs"]
    assert effective_settings(step.tasks) == effective_settings(full["steps"][2].tasks)
    assert result["kwargs"]["flow_name"] == "fine-check"
    assert result["kwargs"]["project_id"] == "project-1"
    assert result["kwargs"]["tags"] == ["fine"]
    assert "skip_execution" not in result["kwargs"]


def test_fine_one_requires_explicit_targets(monkeypatch) -> None:
    fine_one_module = importlib.import_module("qdash.workflow.templates.fine_one")
    monkeypatch.setattr(fine_one_module, "CalibService", FakeCalibService)
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        fine_one_module.fine_one(username="alice", chip_id="64Q")
