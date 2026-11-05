"""Verify the targets, scheduling mode and tasks of the Fake Backend Calibration template."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from qdash.workflow.service.targets import MuxTargets

fake_backend_module = importlib.import_module("qdash.workflow.templates.fake_backend")


class RecordingCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps}


@pytest.fixture(autouse=True)
def recording_calib_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fake_backend_module, "CalibService", RecordingCalibService)


def test_defaults_to_mux_0_to_15_scheduled_like_hardware() -> None:
    result = fake_backend_module.fake_calibration(username="alice", chip_id="fake-64q")

    targets = result["targets"]
    assert isinstance(targets, MuxTargets)
    assert targets.mux_ids == list(range(16)) == fake_backend_module.MUX_IDS
    assert targets.exclude_qids == []
    [step] = result["steps"]
    assert step.tasks == fake_backend_module.FAKE_CALIBRATION_TASKS
    # The hardware templates (bringup, check_waveform) default to the box-aware scheduler.
    assert step.mode == "scheduled"


def test_the_default_mux_list_is_a_copy() -> None:
    result = fake_backend_module.fake_calibration(username="alice", chip_id="fake-64q")
    result["targets"].mux_ids.append(99)

    assert list(range(16)) == fake_backend_module.MUX_IDS


def test_mux_subset_exclusions_and_tasks_narrow_the_run() -> None:
    result = fake_backend_module.fake_calibration(
        username="alice",
        chip_id="fake-64q",
        mux_ids=[9, 15],
        exclude_qids=["37"],
        tasks=["CheckRabi"],
        mode="serial",
    )

    targets = result["targets"]
    assert targets.mux_ids == [9, 15]
    assert targets.exclude_qids == ["37"]
    assert result["steps"][0].tasks == ["CheckRabi"]
    assert result["steps"][0].mode == "serial"


@pytest.mark.parametrize("mux_ids", [None, [9]])
def test_qids_never_override_the_mux_selection(mux_ids: list[int] | None) -> None:
    result = fake_backend_module.fake_calibration(
        username="alice", chip_id="fake-64q", mux_ids=mux_ids, qids=["0", "1"]
    )

    targets = result["targets"]
    assert isinstance(targets, MuxTargets)
    assert targets.mux_ids == (mux_ids if mux_ids is not None else list(range(16)))
