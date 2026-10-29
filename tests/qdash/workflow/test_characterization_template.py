from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from qdash.workflow.service.steps import (
    CustomOneQubit,
    CustomTwoQubit,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets

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
        OneQubitCheck,
        FilterByStatus,
        GenerateCRSchedule,
        CustomOneQubit,
        OneQubitFineTune,
        FilterByStatus,
        CustomOneQubit,
        CustomTwoQubit,
    ]
    assert steps[0].tasks == ["ConfigureEF", *characterization_module.GE_CALIBRATION_TASKS]
    assert steps[2].inverse is False
    assert steps[3].tasks == ["ConfigureEF", *characterization_module.GE_CHARACTERIZATION_TASKS]
    assert steps[3].continue_on_failure is True
    assert steps[3].stop_on_failure_tasks == ("ConfigureEF",)
    assert steps[4].tasks == ["ConfigureEF", *characterization_module.EF_CALIBRATION_TASKS]
    assert steps[6].tasks == ["ConfigureEF", *characterization_module.EF_CHARACTERIZATION_TASKS]
    assert steps[6].continue_on_failure is True
    assert steps[6].stop_on_failure_tasks == ("ConfigureEF",)
    assert steps[7].tasks == ["CheckCouplingStrength"]
    assert steps[7].continue_on_failure is True


def test_ge_only_characterization_uses_ge_configuration() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        qids=["0"],
        run_ef_characterization=False,
        run_jazz=False,
    )

    assert isinstance(result["targets"], QubitTargets)
    steps = result["steps"]
    assert [type(step) for step in steps] == [OneQubitCheck, FilterByStatus, CustomOneQubit]
    assert steps[0].tasks[0] == "Configure"
    assert steps[2].tasks[0] == "Configure"
    assert steps[2].stop_on_failure_tasks == ("Configure",)


def test_jazz_does_not_imply_ef_calibration() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        mux_ids=[0],
        run_ge_characterization=False,
        run_ef_characterization=False,
        run_jazz=True,
        inverse=True,
    )

    steps = result["steps"]
    assert [type(step) for step in steps] == [
        OneQubitCheck,
        FilterByStatus,
        GenerateCRSchedule,
        CustomTwoQubit,
    ]
    assert steps[0].tasks[0] == "Configure"
    assert steps[2].inverse is True
    assert steps[3].tasks == ["CheckCouplingStrength"]


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
            run_jazz=False,
        )

    with pytest.raises(ValueError, match="mux_ids or qids is required"):
        characterization_module.characterization(username="alice", chip_id="64Q")


def test_characterization_exposes_primary_task_parameters() -> None:
    result = characterization_module.characterization(
        username="alice",
        chip_id="64Q",
        qids=["0", "1"],
    )

    parameters = result["kwargs"]["task_parameters"]
    expected_tasks = {
        "Configure",
        "ConfigureEF",
        *characterization_module.GE_CALIBRATION_TASKS,
        *characterization_module.GE_CHARACTERIZATION_TASKS,
        *characterization_module.EF_CALIBRATION_TASKS,
        *characterization_module.EF_CHARACTERIZATION_TASKS,
        *characterization_module.TWO_QUBIT_CHARACTERIZATION_TASKS,
    }
    assert parameters.keys() == expected_tasks
    assert parameters["ConfigureEF"]["run"]["configuration_mode"] == "ge-ef-fh"
    assert (
        characterization_module.SHORT_INTERVAL
        < characterization_module.STANDARD_INTERVAL
        < characterization_module.LONG_INTERVAL
    )
    assert (
        parameters["ReadoutClassification"]["run"]["interval"]
        == characterization_module.LONG_INTERVAL
    )
    assert (
        parameters["CheckThermalExcitation"]["run"]["interval"]
        == characterization_module.LONG_INTERVAL
    )
    assert parameters["CheckThermalExcitation"]["run"]["shots"] > 0


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
    for task_name, settings in result["kwargs"]["task_parameters"].items():
        normalized = normalize_task_settings(task_name, settings)
        validate_task_settings(
            registry[task_name],
            task_name,
            normalized,
            source=f"task_parameters[{task_name!r}]",
        )
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
