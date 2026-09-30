"""Verify the coherence check template task order and execution policy."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets

coherence_check_module = importlib.import_module("qdash.workflow.templates.coherence_check")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "args": self.args, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coherence_check_module, "CalibService", FakeCalibService)


def test_coherence_check_runs_expected_tasks_in_order() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    assert len(result["steps"]) == 1
    step = result["steps"][0]
    assert isinstance(step, CustomOneQubit)
    assert step.name == "coherence_check"
    assert step.mode == "synchronized"
    assert step.tasks == [
        "Configure",
        "CheckChevron",
        "CheckRabi",
        "CheckT1",
        "CheckT2Echo",
        "CheckRamsey",
    ]


def test_coherence_check_uses_coarse_measurement_only_chevron() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    assert result["kwargs"]["task_run_parameters"] == {
        "CheckChevron": {
            "detuning_range": {
                "value": (-0.05, 0.05, 31),
                "value_type": "np.linspace",
            },
            "time_range": {
                "value": (0, 401, 16),
                "value_type": "range",
            },
            "update_calibration_parameters": False,
        },
    }


def test_coherence_check_uses_explicit_qubits() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    assert isinstance(result["targets"], QubitTargets)
    assert result["targets"].qids == ["0", "1"]


def test_coherence_check_prefers_mux_targets_and_preserves_exclusions() -> None:
    result = coherence_check_module.coherence_check(
        username="alice",
        chip_id="64Q",
        mux_ids=[0, 1],
        exclude_qids=["2"],
        qids=["8"],
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0, 1]
    assert result["targets"].exclude_qids == ["2"]


def test_coherence_check_requires_explicit_targets() -> None:
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        coherence_check_module.coherence_check(username="alice", chip_id="64Q")


def test_coherence_check_is_listed_as_a_template() -> None:
    metadata_path = Path(coherence_check_module.__file__).with_name("templates.json")
    templates = json.loads(metadata_path.read_text())

    assert any(
        template["id"] == "coherence_check"
        and template["filename"] == "coherence_check.py"
        and template["function_name"] == "coherence_check"
        for template in templates
    )
