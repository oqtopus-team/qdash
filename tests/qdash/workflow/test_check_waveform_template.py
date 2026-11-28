from __future__ import annotations

import importlib

import pytest

from tests.qdash.workflow.calibration_session_fake import (
    fake_session_class,
    install_fake_session,
)
from tests.qdash.workflow.task_call_helpers import names

check_waveform_module = importlib.import_module("qdash.workflow.templates.check_waveform")


FakeCalibService = fake_session_class()


def test_check_waveform_template_runs_check_waveform_step(monkeypatch) -> None:
    install_fake_session(monkeypatch, check_waveform_module, FakeCalibService)

    result = check_waveform_module.check_waveform(
        username="alice",
        chip_id="16Q-test",
        mux_ids=[0],
    )

    step = result["steps"][0]
    assert step.name == "check_waveform"
    assert names(step.tasks) == ["CheckWaveform"]
    assert step.execution_mode == "parallel_by_mux"


def test_check_waveform_template_sets_default_interval(monkeypatch) -> None:
    install_fake_session(monkeypatch, check_waveform_module, FakeCalibService)

    check_waveform_module.check_waveform(
        username="alice",
        chip_id="16Q-test",
        qids=["0"],
    )

    assert FakeCalibService.last_kwargs is not None
    assert FakeCalibService.last_kwargs["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": 150 * 1024,
    }


def test_check_waveform_template_requires_explicit_targets(monkeypatch) -> None:
    install_fake_session(monkeypatch, check_waveform_module, FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        check_waveform_module.check_waveform(username="alice", chip_id="16Q-test")
