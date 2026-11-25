"""Verify the targets, scheduling mode and tasks of the Fake Backend Calibration template."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from qdash.api.services.flow_service.target_defaults import (
    flow_parameter_names,
    resolve_target_defaults,
)
from qdash.datamodel.flow_targets import FlowTargetOverride
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service.flow_targets import override_target
from qdash.workflow.service.targets import MuxTargets, QubitTargets
from tests.qdash.workflow.calibration_session_fake import FakeContext, install_fake_session
from tests.qdash.workflow.task_call_helpers import names

fake_backend_module = importlib.import_module("qdash.workflow.templates.fake_backend")


@pytest.fixture(autouse=True)
def recording_calib_service(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_session(monkeypatch, fake_backend_module)


def test_the_backend_choice_is_part_of_the_resolved_context() -> None:
    result = fake_backend_module.fake_calibration(
        username="alice", chip_id="fake-64q", backend_name="fake", project_id="p"
    )

    assert result["context"] == FakeContext("alice", "fake-64q", "p", "fake")


def test_defaults_to_mux_0_to_3_scheduled_like_hardware() -> None:
    result = fake_backend_module.fake_calibration(username="alice", chip_id="fake-64q")

    targets = result["targets"]
    assert isinstance(targets, MuxTargets)
    assert targets.mux_ids == list(range(4)) == fake_backend_module.MUX_IDS
    assert targets.exclude_qids == []
    [step] = result["steps"]
    assert names(step.tasks) == names(fake_backend_module.FAKE_CALIBRATION_TASKS)
    # The hardware templates (bringup, check_waveform) default to the box-aware scheduler.
    assert step.execution_mode == "parallel_by_mux"


def test_mux_subset_exclusions_and_tasks_narrow_the_run() -> None:
    result = fake_backend_module.fake_calibration(
        username="alice",
        chip_id="fake-64q",
        mux_ids=[9, 15],
        exclude_qids=["37"],
        tasks=[TaskCall(name="CheckRabi")],
        execution_mode="sequential",
    )

    targets = result["targets"]
    assert targets.mux_ids == [9, 15]
    assert targets.exclude_qids == ["37"]
    assert names(result["steps"][0].tasks) == ["CheckRabi"]
    assert result["steps"][0].execution_mode == "sequential"


def test_qids_select_qubits_when_no_mux_ids_are_given() -> None:
    result = fake_backend_module.fake_calibration(
        username="alice", chip_id="fake-64q", qids=["0", "1"]
    )

    assert result["targets"] == QubitTargets(qids=["0", "1"])


def test_mux_ids_take_precedence_over_qids() -> None:
    result = fake_backend_module.fake_calibration(
        username="alice", chip_id="fake-64q", mux_ids=[9], qids=["0", "1"]
    )

    assert result["targets"] == MuxTargets(mux_ids=[9], exclude_qids=[])


def test_execution_dialog_reads_the_template_default_targets() -> None:
    assert fake_backend_module.__file__ is not None
    source = Path(fake_backend_module.__file__).read_text()

    defaults = resolve_target_defaults(source, "fake_calibration", {})

    assert defaults == FlowTargetOverride(mux_ids=list(range(4)))


@pytest.mark.parametrize(
    "override",
    [
        FlowTargetOverride(mux_ids=[9, 15], exclude_qids=["37"]),
        FlowTargetOverride(qids=["0", "5"]),
    ],
)
def test_template_targets_match_an_execution_override(override: FlowTargetOverride) -> None:
    # FlowService passes the override fields the entrypoint accepts as parameters, and
    # CalibrationSession.run replaces the targets from the run context. Both must agree so the
    # logged and executed targets are the same.
    assert fake_backend_module.__file__ is not None
    source = Path(fake_backend_module.__file__).read_text()
    accepted = flow_parameter_names(source, "fake_calibration")
    parameters = {key: value for key, value in override.model_dump().items() if key in accepted}

    result = fake_backend_module.fake_calibration(
        username="alice", chip_id="fake-64q", **parameters
    )

    assert result["targets"] == override_target(result["targets"], override)
