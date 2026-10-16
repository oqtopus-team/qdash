"""Verify the EF calibration template task order and execution settings."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from qdash.workflow.service.steps import CustomOneQubit
from qdash.workflow.service.targets import MuxTargets, QubitTargets

ef_calibration_module = importlib.import_module("qdash.workflow.templates.ef_calibration")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "args": self.args, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ef_calibration_module, "CalibService", FakeCalibService)


def test_ef_calibration_runs_expected_tasks_in_one_synchronized_step() -> None:
    result = ef_calibration_module.ef_calibration(
        username="alice",
        chip_id="64Q",
        qids=["0"],
    )

    assert len(result["steps"]) == 1
    step = result["steps"][0]
    assert isinstance(step, CustomOneQubit)
    assert step.name == "ef_calibration"
    assert step.mode == "synchronized"
    assert step.tasks == [
        "ConfigureEF",
        "CheckRabi",
        "CreateHPIPulse",
        "CheckEFChevron",
        "CheckEFRabi",
        "CreateEFHPIPulse",
        "CreateEFPIPulse",
        "EFReadoutClassification",
    ]


def test_ef_calibration_forwards_configuration_mode_and_shared_defaults() -> None:
    result = ef_calibration_module.ef_calibration(
        username="alice",
        chip_id="64Q",
        qids=["0"],
        configuration_mode="ge-ef-fh",
        tags=["ef"],
        flow_name="ef-check",
        project_id="project-1",
    )

    assert result["kwargs"] == {
        "flow_name": "ef-check",
        "tags": ["ef"],
        "project_id": "project-1",
        "task_run_parameters": {
            "ConfigureEF": {
                "configuration_mode": {"value": "ge-ef-fh", "value_type": "str"},
            },
            "CreateHPIPulse": {
                "hpi_duration": {"value": 32, "value_type": "int"},
            },
            "CheckEFChevron": {
                "shots": {"value": 256, "value_type": "int"},
            },
            "CreateEFHPIPulse": {
                "ef_hpi_duration": {"value": 32, "value_type": "int"},
            },
            "CreateEFPIPulse": {
                "ef_pi_duration": {"value": 32, "value_type": "int"},
            },
        },
        "default_run_parameters": {
            "readout_duration": {"value": 1024, "value_type": "int"},
            "interval": {"value": 150 * 1024, "value_type": "int"},
        },
    }


def test_ef_calibration_uses_explicit_qubits() -> None:
    result = ef_calibration_module.ef_calibration(username="alice", chip_id="64Q", qids=["0", "1"])

    assert isinstance(result["targets"], QubitTargets)
    assert result["targets"].qids == ["0", "1"]


def test_ef_calibration_prefers_mux_targets_and_preserves_exclusions() -> None:
    result = ef_calibration_module.ef_calibration(
        username="alice",
        chip_id="64Q",
        mux_ids=[0, 1],
        exclude_qids=["2"],
        qids=["8"],
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0, 1]
    assert result["targets"].exclude_qids == ["2"]


def test_ef_calibration_requires_explicit_targets() -> None:
    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        ef_calibration_module.ef_calibration(username="alice", chip_id="64Q")


def test_ef_calibration_is_listed_as_a_template() -> None:
    module_file = ef_calibration_module.__file__
    assert module_file is not None
    metadata_path = Path(module_file).with_name("templates.json")
    templates = json.loads(metadata_path.read_text())

    assert any(
        template["id"] == "ef_calibration"
        and template["filename"] == "ef_calibration.py"
        and template["function_name"] == "ef_calibration"
        for template in templates
    )
