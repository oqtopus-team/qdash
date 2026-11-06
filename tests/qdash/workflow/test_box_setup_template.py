"""Verify the box setup template steps and task settings."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.calibtasks.qubex import CorrectCaptureDelay
from qdash.workflow.engine.task_parameters import normalize_task_parameters
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets

box_setup_module = importlib.import_module("qdash.workflow.templates.box_setup")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(box_setup_module, "CalibService", FakeCalibService)


def test_box_setup_corrects_each_mux() -> None:
    result = box_setup_module.box_setup(
        username="alice", chip_id="64Q", mux_ids=[0, 1], mode="serial"
    )

    assert result["targets"] == MuxTargets(mux_ids=[0, 1], exclude_qids=[])
    (correct,) = result["steps"]
    assert isinstance(correct, BringUp)
    assert correct.tasks == ["CorrectCaptureDelay"]
    assert correct.mode == "serial"


def test_box_setup_settings_match_task_defaults() -> None:
    result = box_setup_module.box_setup(username="alice", chip_id="64Q", mux_ids=[0])

    settings = normalize_task_parameters(result["kwargs"]["task_parameters"])
    run = settings["CorrectCaptureDelay"]["run"]
    for name in ("delay_range", "capture_delay_word_range", "capture_delay_ns_range", "shots"):
        assert run[name]["value"] == CorrectCaptureDelay.run_spec[name].default


def test_box_setup_requires_mux_ids() -> None:
    with pytest.raises(ValueError, match="mux_ids is required"):
        box_setup_module.box_setup(username="alice", chip_id="64Q", qids=["0"])
