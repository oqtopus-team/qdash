"""Verify coarse template targets, stage boundaries, and execution configuration."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.service.steps import OneQubitCheck
from qdash.workflow.service.targets import MuxTargets, QubitTargets

coarse_one_module = importlib.import_module("qdash.workflow.templates.coarse_one")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "args": self.args, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coarse_one_module, "CalibService", FakeCalibService)


def test_coarse_one_configures_before_readout_search_and_calibrates_all_pulses() -> None:
    result = coarse_one_module.coarse_one(username="alice", chip_id="64Q", qids=["0"])

    assert len(result["steps"]) == 1
    step = result["steps"][0]
    assert isinstance(step, OneQubitCheck)
    assert step.mode == "synchronized"
    assert step.tasks == [
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


def test_coarse_one_uses_explicit_qubits() -> None:
    result = coarse_one_module.coarse_one(username="alice", chip_id="64Q", qids=["0", "1"])

    assert isinstance(result["targets"], QubitTargets)
    assert result["targets"].qids == ["0", "1"]


def test_coarse_one_prefers_mux_targets_and_preserves_exclusions() -> None:
    result = coarse_one_module.coarse_one(
        username="alice", chip_id="64Q", mux_ids=[0, 1], exclude_qids=["2"], qids=["8"]
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0, 1]
    assert result["targets"].exclude_qids == ["2"]


def test_coarse_one_requires_explicit_targets() -> None:
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        coarse_one_module.coarse_one(username="alice", chip_id="64Q")


def test_coarse_one_forwards_execution_context_and_preserves_task_scan_defaults() -> None:
    result = coarse_one_module.coarse_one(
        username="alice",
        chip_id="64Q",
        qids=["0"],
        project_id="project-1",
        flow_name="coarse-check",
        tags=["coarse"],
    )

    assert result["args"] == ("alice", "64Q")
    assert result["kwargs"] == {
        "project_id": "project-1",
        "flow_name": "coarse-check",
        "tags": ["coarse"],
        "task_run_parameters": {
            "CreateHPIPulse": {
                "hpi_duration": {"value": 32, "value_type": "int"},
            },
            "CreatePIPulse": {
                "pi_duration": {"value": 32, "value_type": "int"},
            },
            "CreateDRAGHPIPulse": {
                "drag_hpi_duration": {"value": 16, "value_type": "int"},
            },
            "CreateDRAGPIPulse": {
                "drag_pi_duration": {"value": 24, "value_type": "int"},
            },
        },
        "default_run_parameters": {
            "readout_duration": {"value": 2048, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    }
