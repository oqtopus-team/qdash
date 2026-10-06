"""Tests for the calibration-pipeline system flow builder."""

from __future__ import annotations

import pytest

from qdash.datamodel.calibration_pipeline import (
    STEP_CATALOG,
    CalibrationPipelineSpec,
    PipelineStep,
    step_provides,
)
from qdash.workflow.service.pipeline_flow import build_step, build_steps, build_targets
from qdash.workflow.service.steps import (
    CustomOneQubit,
    FilterByMetric,
    GenerateCRSchedule,
    OneQubitCheck,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets

# One instance of every step type the spec allows, with explicit fields.
EVERY_STEP: list[dict[str, object]] = [
    {"type": "ConfigureAll", "mux_ids": [0]},
    {"type": "BringUp", "tasks": ["CheckResonatorSpectroscopy"]},
    {"type": "OneQubitCheck", "mode": "scheduled", "configure": True},
    {"type": "FilterByStatus"},
    {"type": "OneQubitFineTune", "tasks": ["CheckRabi"]},
    {"type": "FilterByMetric", "metric": "t1", "threshold": 30.0},
    {"type": "CustomOneQubit", "step_name": "coh", "tasks": ["CheckT1"], "mode": "serial"},
    {"type": "GenerateCRSchedule", "max_parallel_ops": 4, "inverse": True},
    {"type": "TwoQubitCalibration", "tasks": ["CheckCrossResonance"], "max_parallel_ops": 2},
    {"type": "CustomTwoQubit", "step_name": "zx", "tasks": ["CreateZX90"], "max_parallel_ops": 3},
]


def test_every_catalog_entry_has_a_spec_example() -> None:
    assert {step["type"] for step in EVERY_STEP} == set(STEP_CATALOG)


def test_catalog_matches_the_step_classes() -> None:
    """The API validates with STEP_CATALOG; the worker runs the classes. Keep them equal."""
    parsed = CalibrationPipelineSpec.model_validate(
        {"targets": {"qids": ["0"]}, "steps": EVERY_STEP}
    )
    for spec_step, built in zip(parsed.steps, build_steps(parsed), strict=True):
        entry = STEP_CATALOG[spec_step.type]
        assert built.requires == set(entry.requires), spec_step.type
        assert built.provides == set(step_provides(spec_step)), spec_step.type
        assert type(built).__name__ == spec_step.type


def test_fields_reach_the_step_objects() -> None:
    parsed = CalibrationPipelineSpec.model_validate(
        {"targets": {"qids": ["0"]}, "steps": EVERY_STEP}
    )
    built = build_steps(parsed)
    check = built[2]
    assert isinstance(check, OneQubitCheck)
    assert (check.mode, check.configure, check.tasks) == ("scheduled", True, None)
    metric = built[5]
    assert isinstance(metric, FilterByMetric)
    assert (metric.metric, metric.threshold) == ("t1", 30.0)
    custom = built[6]
    assert isinstance(custom, CustomOneQubit)
    assert (custom.step_name, custom.tasks, custom.mode) == ("coh", ["CheckT1"], "serial")
    schedule = built[7]
    assert isinstance(schedule, GenerateCRSchedule)
    assert (schedule.max_parallel_ops, schedule.inverse) == (4, True)
    two = built[8]
    assert isinstance(two, TwoQubitCalibration)
    assert (two.tasks, two.max_parallel_ops) == (["CheckCrossResonance"], 2)


def test_targets_map_to_target_classes() -> None:
    qubits = CalibrationPipelineSpec.model_validate(
        {"targets": {"qids": ["0", "1"]}, "steps": [{"type": "OneQubitCheck"}]}
    )
    assert build_targets(qubits) == QubitTargets(qids=["0", "1"])
    muxes = CalibrationPipelineSpec.model_validate(
        {
            "targets": {"mux_ids": [0, 1], "exclude_qids": ["5"]},
            "steps": [{"type": "OneQubitCheck"}],
        }
    )
    assert build_targets(muxes) == MuxTargets(mux_ids=[0, 1], exclude_qids=["5"])


def test_unknown_step_object_is_refused() -> None:
    class Rogue:
        type = "Rogue"

    with pytest.raises(ValueError, match="unsupported pipeline step"):
        build_step(Rogue())  # type: ignore[arg-type]


def test_spec_step_type_alias_is_the_union() -> None:
    # Guard against the union silently dropping a member.
    assert len(PipelineStep.__args__[0].__args__) == len(STEP_CATALOG)
