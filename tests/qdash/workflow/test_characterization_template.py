from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from qdash.workflow import sweep
from qdash.workflow.service.steps import (
    ConfigureAll,
    CustomOneQubit,
    CustomTwoQubit,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets
from tests.qdash.workflow.task_call_helpers import effective_settings, names, settings

characterization_module = importlib.import_module("qdash.workflow.templates.characterization")


class FakeCalibService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def run(self, targets: Any, *, steps: list[Any]) -> dict[str, Any]:
        return {"targets": targets, "steps": steps, "kwargs": self.kwargs}


@pytest.fixture(autouse=True)
def fake_calibration_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(characterization_module, "CalibService", FakeCalibService)


def test_characterization_builds_full_pipeline_in_dependency_order() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
    )

    steps = result["steps"]
    assert [type(step) for step in steps] == [
        ConfigureAll,
        OneQubitCheck,
        FilterByStatus,
        GenerateCRSchedule,
        CustomOneQubit,
        OneQubitFineTune,
        FilterByStatus,
        CustomOneQubit,
        CustomTwoQubit,
    ]
    assert names(steps[1].tasks) == names(characterization_module.GE_CALIBRATION_TASKS)
    assert steps[3].inverse is False
    assert names(steps[4].tasks) == names(characterization_module.GE_CHARACTERIZATION_TASKS)
    assert steps[4].continue_on_failure is True
    assert all(call.on_failure is None for call in steps[4].tasks)
    assert names(steps[5].tasks) == names(characterization_module.EF_CALIBRATION_TASKS)
    assert names(steps[7].tasks) == names(characterization_module.EF_CHARACTERIZATION_TASKS)
    assert steps[7].tasks[0].name == "CheckGEFRelaxation"
    assert steps[7].continue_on_failure is True
    assert all(call.on_failure is None for call in steps[7].tasks)
    assert names(steps[8].tasks) == ["CheckCouplingStrength"]
    assert steps[8].step_name == "coupling_characterization"
    assert steps[8].continue_on_failure is True
    assert _configure_all_mode(result) == "ge-ef-fh"
    assert "configuration_mode" not in result["kwargs"]


def test_ge_only_characterization_uses_ge_configuration() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        qids=["0"],
        run_ef_characterization=False,
        run_coupling_characterization=False,
    )

    assert isinstance(result["targets"], QubitTargets)
    steps = result["steps"]
    assert [type(step) for step in steps] == [
        ConfigureAll,
        OneQubitCheck,
        FilterByStatus,
        CustomOneQubit,
    ]
    assert names(steps[1].tasks) == names(characterization_module.GE_CALIBRATION_TASKS)
    assert names(steps[3].tasks) == names(characterization_module.GE_CHARACTERIZATION_TASKS)
    assert all(call.on_failure is None for call in steps[3].tasks)
    assert _configure_all_mode(result) == "ge-cr-cr"


def test_ef_characterization_without_fh_chevron_uses_ef_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        characterization_module,
        "EF_CHARACTERIZATION_TASKS",
        [
            call
            for call in characterization_module.EF_CHARACTERIZATION_TASKS
            if call.name != "CheckAdaptiveFHChevron"
        ],
    )

    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        qids=["0"],
        run_ge_characterization=False,
        run_coupling_characterization=False,
    )

    assert _configure_all_mode(result) == "ge-ef-cr"
    assert _configure_all_mode(result) == "ge-ef-cr"


def test_coupling_characterization_does_not_imply_ef_calibration() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
        run_ge_characterization=False,
        run_ef_characterization=False,
        run_coupling_characterization=True,
        max_parallel_couplings=3,
        reverse_coupling_direction=True,
    )

    steps = result["steps"]
    assert [type(step) for step in steps] == [
        ConfigureAll,
        OneQubitCheck,
        FilterByStatus,
        GenerateCRSchedule,
        CustomTwoQubit,
    ]
    assert names(steps[1].tasks) == names(characterization_module.GE_CALIBRATION_TASKS)
    assert steps[3].inverse is True
    assert steps[3].max_parallel_ops == 3
    assert names(steps[4].tasks) == ["CheckCouplingStrength"]
    assert steps[4].step_name == "coupling_characterization"
    assert steps[4].max_parallel_ops == 3
    assert _configure_all_mode(result) == "ge-cr-cr"


def test_characterization_prefers_mux_targets_and_preserves_exclusions() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
        exclude_qids=["2"],
        qids=["8"],
    )

    assert isinstance(result["targets"], MuxTargets)
    assert result["targets"].mux_ids == [0]
    assert result["targets"].exclude_qids == ["2"]


def test_characterization_requires_targets_and_an_enabled_stage() -> None:
    with pytest.raises(ValueError, match="at least one characterization stage"):
        characterization_module.characterization(
            username="alice",
            chip_id="64Q",
            qids=["0"],
            run_ge_characterization=False,
            run_ef_characterization=False,
            run_coupling_characterization=False,
        )

    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        characterization_module.characterization(username="alice", chip_id="64Q")


def _template_calls(result: dict[str, Any]) -> list[Any]:
    return [call for step in result["steps"] for call in getattr(step, "tasks", None) or ()]


def _configure_all_mode(result: dict[str, Any]) -> Any:
    (call,) = result["steps"][0].calls()
    return call.run["configuration_mode"]["value"]


@pytest.mark.parametrize(
    ("run_ef_characterization", "configuration_mode"),
    [(True, "ge-ef-fh"), (False, "ge-cr-cr")],
)
def test_characterization_sets_the_configure_all_mode_on_its_call(
    run_ef_characterization: bool, configuration_mode: str
) -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
        run_ef_characterization=run_ef_characterization,
    )

    configure_all = result["steps"][0]
    assert isinstance(configure_all, ConfigureAll)
    assert [call.resolved_call_id for call in configure_all.calls()] == ["ConfigureAll"]
    assert _configure_all_mode(result) == configuration_mode
    # Every setting lives on a call; the template no longer passes per-task defaults.
    assert "task_parameters" not in result["kwargs"]
    # The pipeline runs later steps and their workers in the ConfigureAll layout.
    from qdash.workflow.service._internal.session import configured_layout

    assert configured_layout(configure_all) == configuration_mode
    assert result["kwargs"]["default_run_parameters"] == {
        "readout_duration": 1024,
        "interval": characterization_module.STANDARD_INTERVAL,
    }


def test_characterization_calls_carry_their_acquisition_settings() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    calls = _template_calls(result)
    assert names(calls) == [
        *names(characterization_module.GE_CALIBRATION_TASKS),
        *names(characterization_module.GE_CHARACTERIZATION_TASKS),
        *names(characterization_module.EF_CALIBRATION_TASKS),
        *names(characterization_module.EF_CHARACTERIZATION_TASKS),
        *names(characterization_module.COUPLING_CHARACTERIZATION_TASKS),
    ]
    runs = dict(effective_settings(calls))
    # Every call sets its own shots and interval instead of inheriting the shared interval.
    for call_id, call_settings in runs.items():
        assert {"shots", "interval"} <= call_settings["run"].keys(), call_id
    assert (
        characterization_module.SHORT_INTERVAL
        < characterization_module.STANDARD_INTERVAL
        < characterization_module.LONG_INTERVAL
    )
    assert runs["CheckRabi"] == settings(
        run={
            "time_range": sweep.range(0, 401, 8),
            "shots": 2048,
            "interval": characterization_module.SHORT_INTERVAL,
        }
    )
    assert runs["CreateDRAGPIPulse"] == settings(
        run={
            "drag_pi_duration": 24,
            "shots": 2048,
            "interval": characterization_module.STANDARD_INTERVAL,
        }
    )
    assert runs["ReadoutClassification"] == settings(
        run={"shots": 2048, "interval": characterization_module.LONG_INTERVAL}
    )
    assert runs["CheckT1Average"] == settings(
        run={
            "time_range": sweep.logspace(math.log10(100), math.log10(500_000), 51),
            "shots": 1024,
            "interval": characterization_module.STANDARD_INTERVAL,
            "n_runs": 8,
        }
    )
    assert runs["CheckThermalExcitation"] == settings(
        run={"shots": 256 * 1024, "interval": characterization_module.LONG_INTERVAL}
    )
    assert runs["CheckCouplingStrength"] == settings(
        run={
            "time_range": sweep.arange(0, 20_001, 400),
            "shots": 1024,
            "interval": characterization_module.STANDARD_INTERVAL,
        }
    )
    assert runs["CheckGEFRelaxation"] == settings(
        run={
            "time_range": sweep.logspace(math.log10(200), math.log10(200_000), 18),
            "shots": 4096,
            "calibration_shots": 8192,
            "interval": characterization_module.LONG_INTERVAL,
        }
    )


def test_characterization_task_parameters_match_task_specs() -> None:
    from qdash.workflow.calibtasks.active_protocols import generate_task_instances
    from qdash.workflow.calibtasks.base import BaseTask
    from qdash.workflow.engine.task_parameters import (
        normalize_task_settings,
        validate_task_settings,
    )

    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    registry = BaseTask.registry["qubex"]
    calls = [*result["steps"][0].calls(), *_template_calls(result)]
    checked = [
        (f"call {call_id!r}", call.name, call_settings)
        for call, (call_id, call_settings) in zip(calls, effective_settings(calls), strict=True)
    ]
    for source, task_name, task_settings in checked:
        normalized = normalize_task_settings(task_name, task_settings)
        validate_task_settings(registry[task_name], task_name, normalized, source=source)
        instances = generate_task_instances(
            [task_name],
            {
                task_name: {
                    "run": normalized["run"],
                    "input": normalized["input"],
                }
            },
            "qubex",
        )
        assert instances[task_name].get_name() == task_name


def test_characterization_is_listed_as_a_template() -> None:
    module_file = characterization_module.__file__
    assert module_file is not None
    metadata_path = Path(module_file).with_name("templates.json")
    templates = json.loads(metadata_path.read_text())

    assert any(
        template["id"] == "characterization"
        and template["filename"] == "characterization.py"
        and template["function_name"] == "characterization"
        for template in templates
    )
