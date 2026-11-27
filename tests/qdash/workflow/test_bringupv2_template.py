"""Tests for the Bring-up v2 template."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from qdash.api.services.flow_service.flow_metadata import declared_session_name
from qdash.api.services.flow_service.validation import validate_flow_code
from qdash.common.config.backend import get_tasks
from qdash.workflow.calibtasks.active_protocols import generate_task_instances, is_mux_task
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.engine.task_parameters import normalize_task_settings, validate_task_settings
from tests.qdash.workflow.calibration_session_fake import (
    fake_session_class,
    install_fake_session,
)
from tests.qdash.workflow.task_call_helpers import effective_settings, names, settings

bringupv2_module = importlib.import_module("qdash.workflow.templates.bringupv2")
bringup_module = importlib.import_module("qdash.workflow.templates.bringup")

FakeCalibService = fake_session_class()


def test_bringupv2_runs_mapping_between_resonator_and_qubit_spectroscopy(monkeypatch) -> None:
    install_fake_session(monkeypatch, bringupv2_module, FakeCalibService)

    result = bringupv2_module.bringupv2(username="alice", chip_id="16Q-test", mux_ids=[0])

    assert [step.name for step in result["steps"]] == ["bringup"]
    assert names(result["steps"][0].tasks) == [
        "CheckResonatorSpectroscopy",
        "CheckResonatorQubitMapping",
        "CheckQubitSpectroscopy",
        "CheckControlAmplitude",
        "CheckAdaptiveChevron",
    ]


def test_bringupv2_keeps_bringup_settings_and_adds_mapping_settings(monkeypatch) -> None:
    install_fake_session(monkeypatch, bringupv2_module, FakeCalibService)

    result = bringupv2_module.bringupv2(username="alice", chip_id="16Q-test", mux_ids=[0])

    assert FakeCalibService.last_kwargs is not None
    assert FakeCalibService.last_kwargs["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": 150 * 1024,
    }
    assert effective_settings(result["steps"][0].tasks) == [
        ("CheckResonatorSpectroscopy", settings(run={"shots": 1024, "interval": 0})),
        (
            "CheckResonatorQubitMapping",
            settings(
                run={
                    "drive_power": 0.0,
                    "frequency_step": 0.020,
                    "shots": 512,
                    "interval": 1024,
                }
            ),
        ),
        ("CheckQubitSpectroscopy", settings(run={"shots": 1024, "interval": 1024})),
        ("CheckControlAmplitude", settings(run={"shots": 8192})),
        ("CheckAdaptiveChevron", settings(run={"shots": 256})),
    ]


def test_bringupv2_shares_every_other_call_with_bringup() -> None:
    v2_calls = [
        call
        for call in bringupv2_module.BRINGUPV2_TASKS
        if call.name != "CheckResonatorQubitMapping"
    ]

    assert [call.model_dump() for call in v2_calls] == [
        call.model_dump() for call in bringup_module.BRINGUP_TASKS
    ]


def test_bringupv2_requires_explicit_mux_ids(monkeypatch) -> None:
    install_fake_session(monkeypatch, bringupv2_module, FakeCalibService)

    with pytest.raises(ValueError, match="mux_ids is required"):
        bringupv2_module.bringupv2(username="alice", chip_id="16Q-test")


def test_bringupv2_task_settings_match_task_specs(monkeypatch) -> None:
    install_fake_session(monkeypatch, bringupv2_module, FakeCalibService)
    result = bringupv2_module.bringupv2(username="alice", chip_id="16Q-test", mux_ids=[0])
    calls = result["steps"][0].calls()
    registry = BaseTask.registry["qubex"]

    assert set(names(calls)) <= set(get_tasks("qubex"))
    assert is_mux_task("CheckResonatorQubitMapping", "qubex")
    instances = {}
    for call, (task_name, task_settings) in zip(calls, effective_settings(calls), strict=True):
        normalized = normalize_task_settings(task_name, task_settings)
        validate_task_settings(registry[task_name], task_name, normalized, source=call.name)
        instances.update(
            generate_task_instances(
                [task_name],
                {task_name: {"run": normalized["run"], "input": normalized["input"]}},
                "qubex",
            )
        )

    mapping = instances["CheckResonatorQubitMapping"]
    assert mapping.run_parameters["drive_power"].get_value() == 0.0
    assert mapping.run_parameters["frequency_step"].get_value() == pytest.approx(0.020)
    assert mapping.run_parameters["shots"].get_value() == 512
    assert mapping.run_parameters["interval"].get_value() == 1024.0


def test_bringupv2_source_passes_flow_validation() -> None:
    module_file = bringupv2_module.__file__
    assert module_file is not None
    code = Path(module_file).read_text(encoding="utf-8")

    validate_flow_code(code, "bringupv2")
    assert declared_session_name(code, "bringupv2") == "Bring-up v2"


def test_bringupv2_is_listed_as_a_template() -> None:
    module_file = bringupv2_module.__file__
    assert module_file is not None
    templates = json.loads(Path(module_file).with_name("templates.json").read_text())

    entry = next(template for template in templates if template["id"] == "bringupv2")
    bringup_entry = next(template for template in templates if template["id"] == "bringup")
    assert set(entry) == set(bringup_entry)
    assert entry["filename"] == "bringupv2.py"
    assert entry["function_name"] == "bringupv2"
    assert entry["backend"] == "qubex"
    assert entry["category"] == "production"


def test_bringupv2_documents_that_batch_mode_cannot_run_its_tasks() -> None:
    from qdash.workflow.service.one_qubit_stage_runner import batch_capable_tasks

    capable = batch_capable_tasks("qubex")
    unsupported = [name for name in names(bringupv2_module.BRINGUPV2_TASKS) if not capable[name]]

    assert unsupported == ["CheckResonatorQubitMapping", "CheckControlAmplitude"]
    docstring = bringupv2_module.bringupv2.__doc__ or ""
    batch_note = docstring.split('"simultaneous_spectroscopy"', 1)[1]
    assert all(name in batch_note for name in unsupported)
