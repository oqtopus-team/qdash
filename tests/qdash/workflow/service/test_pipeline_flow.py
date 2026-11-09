"""Tests for the calibration-pipeline system flow builder."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.datamodel.calibration_pipeline import (
    STEP_CATALOG,
    CalibrationPipelineSpec,
    PipelineStep,
    step_calls,
    step_provides,
)
from qdash.datamodel.task_call import TaskCall
from qdash.workflow.service.pipeline_flow import (
    build_step,
    build_steps,
    build_targets,
    parse_dispatched_spec,
    pipeline_note,
)
from qdash.workflow.service.steps import (
    CalibrationStep,
    CustomOneQubit,
    FilterByMetric,
    FilterByStatus,
    GenerateCRSchedule,
    OneQubitCheck,
    OneQubitFineTune,
    Pipeline,
    TwoQubitCalibration,
)
from qdash.workflow.service.targets import MuxTargets, QubitTargets

# One instance of every step type the spec allows, with explicit fields.
EVERY_STEP: list[dict[str, object]] = [
    {"type": "ConfigureAll", "mux_ids": [0]},
    {"type": "BringUp", "tasks": [{"name": "CheckResonatorSpectroscopy"}]},
    {"type": "OneQubitCheck", "mode": "scheduled", "configure": True},
    {"type": "FilterByStatus"},
    {"type": "OneQubitFineTune", "tasks": [{"name": "CheckRabi"}]},
    {"type": "FilterByMetric", "metric": "t1", "threshold": 30.0},
    {
        "type": "CustomOneQubit",
        "step_name": "coh",
        "tasks": [
            {"name": "CheckRamsey", "call_id": "ramsey_coarse", "run": {"detuning": 0.001}},
            {"name": "CheckRamsey", "call_id": "ramsey_fine", "run": {"detuning": 0.0002}},
        ],
        "mode": "serial",
        "continue_on_failure": True,
    },
    {"type": "GenerateCRSchedule", "max_parallel_ops": 4, "inverse": True},
    {
        "type": "TwoQubitCalibration",
        "tasks": [{"name": "CheckCrossResonance"}],
        "max_parallel_ops": 2,
    },
    {
        "type": "CustomTwoQubit",
        "step_name": "zx",
        "tasks": [{"name": "CreateZX90"}],
        "max_parallel_ops": 3,
    },
]


def spec(steps: list[dict[str, Any]], **fields: Any) -> CalibrationPipelineSpec:
    return CalibrationPipelineSpec.model_validate(
        {"spec_version": 2, "targets": {"qids": ["0"]}, "steps": steps, **fields}
    )


def test_every_catalog_entry_has_a_spec_example() -> None:
    assert {step["type"] for step in EVERY_STEP} == set(STEP_CATALOG)


def test_catalog_matches_the_step_classes() -> None:
    """The API validates with STEP_CATALOG; the worker runs the classes. Keep them equal."""
    parsed = spec(EVERY_STEP)
    Pipeline(build_steps(parsed))  # the worker accepts every spec the API accepts
    for spec_step, built in zip(parsed.steps, build_steps(parsed), strict=True):
        entry = STEP_CATALOG[spec_step.type]
        assert built.requires == set(entry.requires), spec_step.type
        provided = set(built.provides)
        if isinstance(built, CalibrationStep):
            provided.add(built.resolved_step_id)
            if entry.task_scope is not None:
                # The API resolves the same calls, in the same order, as the worker runs.
                assert list(built.calls()) == step_calls(spec_step), spec_step.type
            if entry.one_qubit_result:
                metrics = getattr(built, "step_metrics", ())
                assert tuple(metrics) == entry.step_metrics, spec_step.type
        assert provided == set(step_provides(spec_step)), spec_step.type
        assert type(built).__name__ == spec_step.type


def test_fields_reach_the_step_objects() -> None:
    parsed = spec(EVERY_STEP)
    built = build_steps(parsed)
    check = built[2]
    assert isinstance(check, OneQubitCheck)
    assert (check.mode, check.configure, check.tasks) == ("scheduled", True, None)
    assert next(call.name for call in check.calls()) == "Configure"
    metric = built[5]
    assert isinstance(metric, FilterByMetric)
    assert (metric.metric, metric.threshold, metric.step) == ("t1", 30.0, None)
    custom = built[6]
    assert isinstance(custom, CustomOneQubit)
    assert (custom.step_name, custom.mode, custom.continue_on_failure) == ("coh", "serial", True)
    assert [(call.call_id, call.run) for call in custom.tasks] == [
        ("ramsey_coarse", {"detuning": {"value": 0.001}}),
        ("ramsey_fine", {"detuning": {"value": 0.0002}}),
    ]
    schedule = built[7]
    assert isinstance(schedule, GenerateCRSchedule)
    assert (schedule.max_parallel_ops, schedule.inverse) == (4, True)
    two = built[8]
    assert isinstance(two, TwoQubitCalibration)
    assert (two.tasks, two.max_parallel_ops) == (
        [TaskCall(name="CheckCrossResonance", call_id="CheckCrossResonance")],
        2,
    )


def test_filter_references_and_step_ids_reach_the_step_objects() -> None:
    parsed = spec(
        [
            {"type": "OneQubitCheck", "step_id": "coarse"},
            {
                "type": "CustomOneQubit",
                "step_name": "ramsey",
                "tasks": [
                    {"name": "CheckRamsey", "call_id": "coarse"},
                    {"name": "CheckRamsey", "call_id": "fine"},
                ],
            },
            {"type": "FilterByStatus", "step": "coarse"},
            {
                "type": "FilterByMetric",
                "step": "ramsey",
                "call_id": "fine",
                "metric": "t2_star",
                "threshold": 10.0,
            },
        ]
    )
    built = build_steps(parsed)
    Pipeline(built)
    assert isinstance(built[0], OneQubitCheck)
    assert built[0].resolved_step_id == "coarse"
    status = built[2]
    assert isinstance(status, FilterByStatus)
    assert (status.step, status.call_id) == ("coarse", None)
    metric = built[3]
    assert isinstance(metric, FilterByMetric)
    assert (metric.step, metric.call_id, metric.metric) == ("ramsey", "fine", "t2_star")


def test_queued_version_1_spec_is_converted_at_the_flow_boundary() -> None:
    logger = MagicMock()
    parsed = parse_dispatched_spec(
        {
            "targets": {"qids": ["0"]},
            "steps": [{"type": "CustomOneQubit", "tasks": ["CheckRabi", "CheckRabi"]}],
            "task_run_parameters": {"CheckRabi": {"shots": 512}},
        },
        logger,
    )
    assert parsed.spec_version == 2
    assert [call.call_id for call in step_calls(parsed.steps[0])] == ["CheckRabi", "CheckRabi_2"]
    assert parsed.canonical_task_parameters() == {
        "CheckRabi": {"run": {"shots": {"value": 512}}, "input": {}}
    }
    logger.warning.assert_called_once()


def test_queued_version_1_spec_with_repeated_builtin_steps_builds() -> None:
    logger = MagicMock()
    parsed = parse_dispatched_spec(
        {
            "targets": {"qids": ["0"]},
            "steps": [
                {"type": "OneQubitCheck"},
                {"type": "FilterByStatus"},
                {"type": "OneQubitCheck", "tasks": ["CheckRabi"]},
                {"type": "FilterByStatus"},
            ],
        },
        logger,
    )
    built = build_steps(parsed)
    assert [step.name for step in built] == [
        "one_qubit_check",
        "filter_by_status",
        "one_qubit_check_2",
        "filter_by_status",
    ]
    # Reference-free filters still read the latest built-in one-qubit result.
    assert all(step.step is None for step in built if isinstance(step, FilterByStatus))
    Pipeline(built)  # the worker's own step-chain validation accepts the plan
    assert "one_qubit_check_2" in logger.warning.call_args.args[0]


@pytest.mark.parametrize("step_class", [OneQubitCheck, OneQubitFineTune])
def test_python_steps_share_the_configure_call_policy(step_class: Any) -> None:
    with pytest.raises(ValueError, match="configure=True already runs Configure"):
        step_class(configure=True, tasks=[TaskCall(name="Configure", call_id="explicit")])
    step = step_class(configure=True, tasks=[TaskCall(name="CheckRabi")])
    assert [call.call_id for call in step.calls()] == ["Configure", "CheckRabi"]


def test_version_2_spec_is_not_converted() -> None:
    logger = MagicMock()
    parsed = parse_dispatched_spec(
        {"spec_version": 2, "targets": {"qids": ["0"]}, "steps": [{"type": "OneQubitCheck"}]},
        logger,
    )
    assert parsed.spec_version == 2
    logger.warning.assert_not_called()


def test_targets_map_to_target_classes() -> None:
    qubits = CalibrationPipelineSpec.model_validate(
        {"spec_version": 2, "targets": {"qids": ["0", "1"]}, "steps": [{"type": "OneQubitCheck"}]}
    )
    assert build_targets(qubits) == QubitTargets(qids=["0", "1"])
    muxes = CalibrationPipelineSpec.model_validate(
        {
            "spec_version": 2,
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


def test_pipeline_note_lists_the_plan_with_step_kinds() -> None:
    parsed = spec(
        [
            {"type": "OneQubitCheck"},
            {"type": "FilterByStatus"},
            {"type": "CustomOneQubit", "step_name": "coherence", "tasks": [{"name": "CheckT1"}]},
        ],
        name="coarse-then-coherence",
    )
    note = pipeline_note(parsed, build_steps(parsed))
    assert note == {
        "pipeline": {
            "name": "coarse-then-coherence",
            "spec_version": 2,
            "spec_digest": parsed.plan_digest(),
            "steps": [
                {
                    "index": 1,
                    "name": "one_qubit_check",
                    "step_id": "one_qubit_check",
                    "type": "OneQubitCheck",
                    "kind": "calibration",
                },
                {
                    "index": 2,
                    "name": "filter_by_status",
                    "step_id": None,
                    "type": "FilterByStatus",
                    "kind": "transform",
                },
                {
                    "index": 3,
                    "name": "coherence",
                    "step_id": "coherence",
                    "type": "CustomOneQubit",
                    "kind": "calibration",
                },
            ],
        }
    }
