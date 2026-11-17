"""Verify the Bring-up v2 template's calls, targets, and execution modes."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any, get_type_hints

import pytest
from pydantic import TypeAdapter, ValidationError

from qdash.api.services.flow_service.templates import TemplateCatalog
from qdash.workflow.calibtasks.qubex import (
    CheckAdaptiveChevron,
    CheckControlAmplitude,
    CheckQubitFrequencyMapping,
    CheckResonatorSpectroscopy,
)
from qdash.workflow.engine.task.backend_saver import resolve_publish_targets
from qdash.workflow.service.steps import BringUp
from qdash.workflow.service.targets import MuxTargets
from tests.qdash.workflow.task_call_helpers import effective_settings, names, settings

template_module = importlib.import_module("qdash.workflow.templates.bringupv2")
bringup_module = importlib.import_module("qdash.workflow.templates.bringup")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calib_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(template_module, "CalibService", FakeCalibService)


def _run(**kwargs: Any) -> dict[str, Any]:
    params: dict[str, Any] = {"username": "alice", "chip_id": "16Q", "mux_ids": [0]}
    params.update(kwargs)
    result: dict[str, Any] = template_module.bringupv2(**params)
    return result


def _step(result: dict[str, Any]) -> BringUp:
    (step,) = result["steps"]
    assert isinstance(step, BringUp)
    return step


def test_template_is_registered_and_served_by_the_catalog() -> None:
    module_file = template_module.__file__
    assert module_file is not None
    catalog = TemplateCatalog(templates_dir=Path(module_file).parent)

    listed = {template.id: template for template in catalog.list_templates(backend="qubex")}
    entry = listed["bringupv2"]
    assert entry.name == "Bring-up v2"
    assert entry.filename == "bringupv2.py"
    assert entry.function_name == "bringupv2"
    assert "amachino/qubex#472" in entry.description
    assert "qubit_frequency_mapping" not in listed
    assert listed["bringup"].filename == "bringup.py"
    template = catalog.get_template("bringupv2")
    assert "def bringupv2(" in template.code
    assert "https://github.com/amachino/qubex/pull/472" in template.code
    assert "bringupv2" not in {template.id for template in catalog.list_templates(backend="fake")}


def test_template_runs_detection_mapping_amplitude_and_chevron_in_one_bringup_step() -> None:
    step = _step(_run())

    assert step.name == "bringup"
    assert names(step.calls()) == [
        "CheckResonatorSpectroscopy",
        "CheckQubitFrequencyMapping",
        "CheckControlAmplitude",
        "CheckAdaptiveChevron",
    ]
    assert CheckResonatorSpectroscopy.is_mux_level is True
    for task in (CheckQubitFrequencyMapping, CheckControlAmplitude, CheckAdaptiveChevron):
        assert getattr(task, "is_mux_level", False) is False


def test_template_calls_carry_detection_publication_and_acquisition_settings() -> None:
    step = _step(_run())

    assert effective_settings(step.calls()) == [
        (
            "CheckResonatorSpectroscopy",
            settings(
                run={"shots": 1024, "interval": 0, "detection_only": True},
                update_calibration_parameters=True,
            ),
        ),
        (
            "CheckQubitFrequencyMapping",
            settings(
                run={"shots": 1024, "interval": 1024},
                update_calibration_parameters=True,
            ),
        ),
        ("CheckControlAmplitude", settings(run={"shots": 8192})),
        ("CheckAdaptiveChevron", settings(run={"shots": 256})),
    ]


def test_amplitude_and_chevron_reuse_the_bringup_acquisition_settings() -> None:
    """The last two calls match the Bring-up template's calls exactly."""
    calls = {call.name: call for call in _step(_run()).calls()}
    bringup_calls = {call.name: call for call in bringup_module.BRINGUP_TASKS}

    for name in ("CheckControlAmplitude", "CheckAdaptiveChevron"):
        assert calls[name].settings() == bringup_calls[name].settings()
        assert calls[name].input is None


def test_mapping_outputs_cover_the_amplitude_and_chevron_inputs() -> None:
    """Every required input of the later tasks is a destination the mapping publishes."""
    mapping = CheckQubitFrequencyMapping()
    targets = resolve_publish_targets(mapping, mapping.output_parameters)
    published = {target for names in targets.values() for target in names}
    for task in (CheckControlAmplitude, CheckAdaptiveChevron):
        for name, spec in task.input_spec.items():
            assert {name, *spec.fallback_parameter_names} & published, (task.name, name)


def test_template_leaves_sweep_ranges_and_assignment_order_to_task_defaults() -> None:
    step = _step(_run())

    for call in step.calls():
        run = call.run or {}
        assert "frequency_range" not in run
        assert "power_range" not in run
        assert "resonator_assignment_order" not in run
    assert CheckResonatorSpectroscopy.run_spec["frequency_range"].default is None
    assert CheckQubitFrequencyMapping.run_spec["frequency_range"].default is None


def test_template_shares_bringup_session_defaults() -> None:
    result = _run()

    assert "task_parameters" not in result["kwargs"]
    assert result["kwargs"]["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": 150 * 1024,
    }


def test_template_does_not_change_the_bringup_template() -> None:
    assert names(bringup_module.BRINGUP_TASKS) == [
        "CheckResonatorSpectroscopy",
        "CheckQubitSpectroscopy",
        "CheckControlAmplitude",
        "CheckAdaptiveChevron",
    ]
    (resonator,) = [
        call for call in bringup_module.BRINGUP_TASKS if call.name == "CheckResonatorSpectroscopy"
    ]
    assert "detection_only" not in (resonator.run or {})


def test_template_defaults_to_sequential_and_accepts_parallel_by_mux() -> None:
    assert _step(_run()).execution_mode == "sequential"
    assert _step(_run(execution_mode="parallel_by_mux")).execution_mode == "parallel_by_mux"


@pytest.mark.parametrize("mode", ["parallel_by_round", "simultaneous_spectroscopy", "manual"])
def test_template_rejects_modes_that_can_reorder_a_mux(mode: str) -> None:
    with pytest.raises(ValueError, match="Unknown execution_mode"):
        _run(execution_mode=mode)


def test_flow_run_parameter_type_accepts_only_mux_ordered_modes() -> None:
    fn = getattr(template_module.bringupv2, "fn", template_module.bringupv2)
    assert inspect.signature(fn).parameters["execution_mode"].default == "sequential"
    adapter = TypeAdapter(get_type_hints(fn)["execution_mode"])
    for mode in ("sequential", "parallel_by_mux"):
        assert adapter.validate_python(mode) == mode
    for mode in ("parallel_by_round", "simultaneous_spectroscopy"):
        with pytest.raises(ValidationError):
            adapter.validate_python(mode)


def test_template_requires_explicit_mux_ids() -> None:
    with pytest.raises(ValueError, match="mux_ids is required"):
        template_module.bringupv2(username="alice", chip_id="16Q")


def test_template_targets_muxes_and_ignores_qids() -> None:
    result = _run(mux_ids=[0, 1], qids=["8"], tags=["mapping"], flow_name="f", project_id="p")
    step = _step(result)

    targets = result["targets"]
    assert isinstance(targets, MuxTargets)
    assert (targets.mux_ids, targets.exclude_qids) == ([0, 1], [])
    assert result["kwargs"]["tags"] == ["mapping"]
    assert result["kwargs"]["flow_name"] == "f"
    assert result["kwargs"]["project_id"] == "p"
    assert len(step.calls()) == 4


@pytest.mark.parametrize("exclude_qids", [["2", "Q05"], ["1", "4"], ["Q04"]])
def test_template_forwards_exclusions_like_bringup(exclude_qids: list[str]) -> None:
    """Exclusions, MUX representatives included, reach the targets unchanged."""
    result = _run(mux_ids=[0, 1], exclude_qids=exclude_qids)

    assert result["targets"] == MuxTargets(mux_ids=[0, 1], exclude_qids=exclude_qids)
