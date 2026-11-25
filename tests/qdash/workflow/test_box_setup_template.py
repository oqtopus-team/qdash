"""Verify the box setup template steps and task settings."""

from __future__ import annotations

import importlib

import pytest

from qdash.workflow.calibtasks.qubex import CorrectCaptureDelay
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets
from tests.qdash.workflow.calibration_session_fake import (
    fake_session_class,
    install_fake_session,
)
from tests.qdash.workflow.task_call_helpers import effective_settings, names

box_setup_module = importlib.import_module("qdash.workflow.templates.box_setup")


FakeCalibService = fake_session_class()


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_session(monkeypatch, box_setup_module, FakeCalibService)


def test_box_setup_corrects_each_mux() -> None:
    result = box_setup_module.box_setup(
        username="alice", chip_id="64Q", mux_ids=[0, 1], execution_mode="sequential"
    )

    assert result["targets"] == MuxTargets(mux_ids=[0, 1], exclude_qids=[])
    (correct,) = result["steps"]
    assert isinstance(correct, BringUp)
    assert names(correct.tasks) == ["CorrectCaptureDelay"]
    assert correct.execution_mode == "sequential"


def test_box_setup_settings_match_task_defaults() -> None:
    result = box_setup_module.box_setup(username="alice", chip_id="64Q", mux_ids=[0])

    assert "task_parameters" not in result["kwargs"]
    assert result["kwargs"]["default_run_parameters"] == {"readout_duration": 1024}
    ((call_id, call_settings),) = effective_settings(result["steps"][0].tasks)
    assert call_id == "CorrectCaptureDelay"
    run = call_settings["run"]
    assert set(run) == {
        "delay_range",
        "capture_delay_word_range",
        "capture_delay_ns_range",
        "shots",
    }
    for name in run:
        assert run[name]["value"] == CorrectCaptureDelay.run_spec[name].default


def test_box_setup_requires_mux_ids() -> None:
    with pytest.raises(ValueError, match="mux_ids is required"):
        box_setup_module.box_setup(username="alice", chip_id="64Q", qids=["0"])
