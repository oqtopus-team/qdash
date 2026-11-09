"""Verify the simple calibration template calls and their settings."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.datamodel.task_call import TaskCall, TaskNameNotCallError
from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets
from tests.qdash.workflow.task_call_helpers import effective_settings, settings

simple_module = importlib.import_module("qdash.workflow.templates.simple")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(simple_module, "CalibService", FakeCalibService)


def _step(result: dict[str, Any]) -> CustomOneQubit:
    (step,) = result["steps"]
    assert isinstance(step, CustomOneQubit)
    return step


def test_simple_calibration_default_calls_carry_the_hpi_duration() -> None:
    result = simple_module.simple_calibration(username="alice", chip_id="64Q", mux_ids=[0])

    step = _step(result)
    assert step.name == "simple_tasks"
    assert step.mode == "scheduled"
    assert effective_settings(step.tasks) == [
        ("CheckRabi", settings()),
        ("CreateHPIPulse", settings(run={"hpi_duration": 32})),
        ("CheckHPIPulse", settings()),
    ]
    assert "task_parameters" not in result["kwargs"]
    assert result["kwargs"]["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": 150 * 1024,
    }


def test_simple_calibration_custom_calls_keep_only_their_own_settings() -> None:
    tasks = [
        TaskCall(name="CheckRabi", run={"shots": 512}),
        TaskCall(
            name="CreateHPIPulse",
            call_id="hpi_default",
            run={"shots": 2048},
            input={"control_amplitude": 0.05},
            update_calibration_parameters=False,
            on_failure="continue",
        ),
        TaskCall(name="CreateHPIPulse", call_id="hpi_override", run={"hpi_duration": 48}),
        TaskCall(name="CheckRamsey"),
    ]
    original = list(tasks)

    result = simple_module.simple_calibration(
        username="alice", chip_id="64Q", qids=["0"], tasks=tasks, mode="serial"
    )

    step = _step(result)
    assert step.mode == "serial"
    # Order, ids, duplicates, failure policy, and the user's own values are kept;
    # the default hpi_duration is not added to custom calls.
    assert [(call.resolved_call_id, call.on_failure) for call in step.tasks] == [
        ("CheckRabi", None),
        ("hpi_default", "continue"),
        ("hpi_override", None),
        ("CheckRamsey", None),
    ]
    assert effective_settings(step.tasks) == [
        ("CheckRabi", settings(run={"shots": 512})),
        (
            "hpi_default",
            settings(
                run={"shots": 2048},
                input={"control_amplitude": 0.05},
                update_calibration_parameters=False,
            ),
        ),
        ("hpi_override", settings(run={"hpi_duration": 48})),
        ("CheckRamsey", settings()),
    ]
    # The caller's list and calls are left as they were.
    assert tasks == original
    assert tasks[1].run == {"shots": {"value": 2048}}


def test_simple_calibration_accepts_mapping_entries_as_given() -> None:
    result = simple_module.simple_calibration(
        username="alice",
        chip_id="64Q",
        qids=["0"],
        tasks=[{"name": "CreateHPIPulse"}],
    )

    assert effective_settings(_step(result).tasks) == [("CreateHPIPulse", settings())]


def test_simple_calibration_keeps_an_empty_task_list_empty() -> None:
    result = simple_module.simple_calibration(username="alice", chip_id="64Q", qids=["0"], tasks=[])

    assert _step(result).tasks == []


def test_simple_calibration_still_rejects_repeats_without_call_ids() -> None:
    with pytest.raises(ValueError, match="give every occurrence its own call_id"):
        simple_module.simple_calibration(
            username="alice",
            chip_id="64Q",
            qids=["0"],
            tasks=[TaskCall(name="CreateHPIPulse"), TaskCall(name="CreateHPIPulse")],
        )


def test_simple_calibration_still_rejects_plain_task_names() -> None:
    with pytest.raises(TaskNameNotCallError):
        simple_module.simple_calibration(
            username="alice",
            chip_id="64Q",
            qids=["0"],
            tasks=["CreateHPIPulse"],
        )


def test_simple_calibration_prefers_mux_targets() -> None:
    result = simple_module.simple_calibration(
        username="alice", chip_id="64Q", mux_ids=[0, 1], exclude_qids=["2"], qids=["8"]
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0, 1]
    assert result["targets"].exclude_qids == ["2"]


def test_simple_calibration_uses_explicit_qubits_and_requires_targets() -> None:
    result = simple_module.simple_calibration(username="alice", chip_id="64Q", qids=["0", "1"])

    assert isinstance(result["targets"], QubitTargets)
    assert result["targets"].qids == ["0", "1"]
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        simple_module.simple_calibration(username="alice", chip_id="64Q")
