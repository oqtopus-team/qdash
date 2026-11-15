"""Verify the coherence limit template steps and call settings."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.service.steps import CustomOneQubit, CustomTwoQubit, GenerateCRSchedule
from qdash.workflow.service.targets import MuxTargets, QubitTargets
from tests.qdash.workflow.task_call_helpers import effective_settings, settings

coherence_limit_module = importlib.import_module("qdash.workflow.templates.coherence_limit")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coherence_limit_module, "CalibService", FakeCalibService)


def test_coherence_limit_sets_the_1q_gate_duration_on_its_call() -> None:
    result = coherence_limit_module.coherence_limit(
        username="alice", chip_id="64Q", qids=["0", "1"], execution_mode="sequential"
    )

    one_qubit, schedule, two_qubit = result["steps"]
    assert isinstance(one_qubit, CustomOneQubit)
    assert one_qubit.name == "coherence_limit_1q"
    assert one_qubit.execution_mode == "sequential"
    assert isinstance(schedule, GenerateCRSchedule)
    assert isinstance(two_qubit, CustomTwoQubit)
    assert two_qubit.name == "coherence_limit_2q"
    assert effective_settings(one_qubit.tasks) == [
        ("Check1QGateCoherenceLimit", settings(run={"drag_hpi_duration": 16})),
    ]
    # The 2Q limit keeps the task's own defaults; nothing else is configured.
    assert effective_settings(two_qubit.tasks) == [("Check2QGateCoherenceLimit", settings())]
    assert result["kwargs"] == {"flow_name": None, "tags": None, "project_id": None}


def test_coherence_limit_prefers_mux_targets_and_requires_targets() -> None:
    result = coherence_limit_module.coherence_limit(
        username="alice", chip_id="64Q", mux_ids=[0], exclude_qids=["2"], qids=["8"]
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0]
    assert result["targets"].exclude_qids == ["2"]
    assert result["steps"][0].execution_mode == "parallel_by_mux"

    qubits = coherence_limit_module.coherence_limit(username="alice", chip_id="64Q", qids=["0"])
    assert isinstance(qubits["targets"], QubitTargets)
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        coherence_limit_module.coherence_limit(username="alice", chip_id="64Q")
