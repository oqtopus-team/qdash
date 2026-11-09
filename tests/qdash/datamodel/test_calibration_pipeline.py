"""Tests for the declarative calibration pipeline spec (version 2)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from qdash.datamodel import sweep
from qdash.datamodel.calibration_pipeline import (
    CHECK_1Q_TASKS,
    FULL_1Q_TASKS,
    FULL_2Q_TASKS,
    STEP_CATALOG,
    CalibrationPipelineSpec,
    migrate_pipeline_spec,
    pipeline_spec_json_schema,
    pipeline_warnings,
    step_calls,
    step_id,
    step_tasks,
)
from qdash.datamodel.task_call import TaskCall, normalize_calls


def spec(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "spec_version": 2,
        "targets": {"qids": ["0", "1"]},
        "steps": [{"type": "OneQubitCheck"}],
    }
    base.update(overrides)
    return base


def parse(**overrides: object) -> CalibrationPipelineSpec:
    return CalibrationPipelineSpec.model_validate(spec(**overrides))


def names(calls: list[TaskCall]) -> list[str]:
    return [call.name for call in calls]


def test_defaults_fill_in_the_template_task_lists() -> None:
    parsed = parse(steps=[{"type": "OneQubitCheck"}, {"type": "TwoQubitCalibration"}])
    assert step_tasks(parsed.steps[0]) == names(CHECK_1Q_TASKS)
    assert step_tasks(parsed.steps[1]) == names(FULL_2Q_TASKS)
    assert [call.call_id for call in step_calls(parsed.steps[0])] == names(CHECK_1Q_TASKS)
    assert parsed.name == "pipeline"
    assert parsed.all_tasks() == names(CHECK_1Q_TASKS) + names(FULL_2Q_TASKS)


def test_default_lists_are_valid_call_lists() -> None:
    for entry in STEP_CATALOG.values():
        normalize_calls(entry.default_tasks)
    normalize_calls(FULL_1Q_TASKS)


def test_spec_version_is_required() -> None:
    with pytest.raises(ValidationError, match="spec_version"):
        CalibrationPipelineSpec.model_validate(
            {"targets": {"qids": ["0"]}, "steps": [{"type": "OneQubitCheck"}]}
        )


def test_targets_need_exactly_one_kind() -> None:
    with pytest.raises(ValidationError, match="exactly one of qids or mux_ids"):
        parse(targets={})
    with pytest.raises(ValidationError, match="exactly one of qids or mux_ids"):
        parse(targets={"qids": ["0"], "mux_ids": [0]})
    with pytest.raises(ValidationError, match="exclude_qids only applies"):
        parse(targets={"qids": ["0"], "exclude_qids": ["1"]})
    parsed = parse(targets={"mux_ids": [0, 1], "exclude_qids": ["5"]})
    assert parsed.targets.mux_ids == [0, 1]


def test_filters_need_a_one_qubit_step_before_them() -> None:
    with pytest.raises(ValidationError, match="needs one_qubit_check or one_qubit_fine_tune"):
        parse(steps=[{"type": "FilterByStatus"}])
    # Either one-qubit step satisfies the filter, as in Pipeline._validate.
    parse(steps=[{"type": "OneQubitFineTune"}, {"type": "FilterByStatus"}])
    parse(
        steps=[
            {"type": "OneQubitCheck"},
            {"type": "FilterByMetric", "metric": "t1", "threshold": 30},
            {"type": "GenerateCRSchedule"},
            {"type": "TwoQubitCalibration"},
        ]
    )


def test_unknown_step_types_and_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="does not match any of the expected tags"):
        parse(steps=[{"type": "RunShell"}])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse(steps=[{"type": "OneQubitCheck", "command": "rm -rf /"}])
    with pytest.raises(ValidationError):
        parse(steps=[{"type": "OneQubitCheck", "mode": "parallel"}])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse(
            steps=[
                {
                    "type": "CustomOneQubit",
                    "tasks": [{"name": "CheckT1", "parameters": {"shots": 1}}],
                }
            ]
        )


def test_custom_steps_need_tasks_and_unique_names() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        parse(steps=[{"type": "CustomOneQubit", "tasks": []}])
    with pytest.raises(ValidationError, match="reuses step_id 'a'"):
        parse(
            steps=[
                {"type": "CustomOneQubit", "step_name": "a", "tasks": [{"name": "CheckT1"}]},
                {"type": "CustomOneQubit", "step_name": "a", "tasks": [{"name": "CheckT2Echo"}]},
            ]
        )
    parsed = parse(
        steps=[
            {"type": "CustomOneQubit", "step_name": "coh", "tasks": [{"name": "CheckT1"}]},
            {"type": "CustomOneQubit", "tasks": [{"name": "CheckRamsey"}]},
        ]
    )
    assert [step.step_name for step in parsed.steps] == ["coh", "custom_one_qubit"]  # type: ignore[union-attr]


def test_task_names_are_not_calls() -> None:
    with pytest.raises(ValidationError, match=r"is the task name 'CheckT1'.*TaskCall"):
        parse(steps=[{"type": "CustomOneQubit", "tasks": ["CheckT1"]}])


def test_repeated_builtin_steps_need_their_own_step_ids() -> None:
    with pytest.raises(ValidationError, match="reuses step_id 'one_qubit_check'"):
        parse(steps=[{"type": "OneQubitCheck"}, {"type": "OneQubitCheck"}])
    parsed = parse(
        steps=[
            {"type": "OneQubitCheck", "step_id": "check_before"},
            {"type": "OneQubitCheck", "step_id": "check_after"},
        ]
    )
    assert [step["step_id"] for step in parsed.plan()["steps"]] == ["check_before", "check_after"]


# ---------------------------------------------------------------- task calls


def test_the_same_task_runs_twice_in_one_step_with_its_own_settings() -> None:
    parsed = parse(
        steps=[
            {
                "type": "CustomOneQubit",
                "step_name": "ramsey",
                "tasks": [
                    {"name": "CheckRamsey", "call_id": "coarse", "run": {"detuning": 0.001}},
                    {"name": "CheckRamsey", "call_id": "fine", "run": {"detuning": 0.0002}},
                ],
            }
        ]
    )
    calls = step_calls(parsed.steps[0])
    assert [(call.call_id, call.run) for call in calls] == [
        ("coarse", {"detuning": {"value": 0.001}}),
        ("fine", {"detuning": {"value": 0.0002}}),
    ]
    assert parsed.all_tasks() == ["CheckRamsey", "CheckRamsey"]


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        (
            [{"name": "CheckRamsey"}, {"name": "CheckRamsey", "call_id": "fine"}],
            r"runs 2 times in this step; give every occurrence its own call_id "
            r"\(missing at tasks\[0\]\)",
        ),
        (
            [{"name": "CheckT1", "call_id": "x"}, {"name": "CheckT2Echo", "call_id": "x"}],
            r"tasks\[1\] reuses call_id 'x'",
        ),
        # A default id may not collide with an explicit one.
        (
            [{"name": "CheckT1"}, {"name": "CheckT2Echo", "call_id": "CheckT1"}],
            r"reuses call_id 'CheckT1'",
        ),
        ([{"name": "CheckT1", "call_id": "1st"}], "String should match pattern"),
        ([{"name": "check t1"}], "String should match pattern"),
    ],
)
def test_call_id_rules(tasks: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse(steps=[{"type": "CustomOneQubit", "tasks": tasks}])


def test_call_ids_accept_task_style_names() -> None:
    [call] = normalize_calls([TaskCall(name="CheckRamsey")])
    assert call.call_id == "CheckRamsey"
    assert TaskCall(name="CheckRamsey", call_id="Ramsey.fine-2").call_id == "Ramsey.fine-2"


def test_absent_call_settings_inherit_instead_of_resetting() -> None:
    defaults = {
        "CheckRabi": {
            "run": {"shots": {"value": 512}},
            "input": {},
            "update_calibration_parameters": False,
        }
    }
    inherit = TaskCall(name="CheckRabi", run={"interval": 1})
    assert "update_calibration_parameters" not in inherit.settings()
    effective = inherit.effective_settings(defaults)
    assert effective["update_calibration_parameters"] is False
    assert effective["run"] == {"shots": {"value": 512}, "interval": {"value": 1}}
    override = TaskCall(name="CheckRabi", run={"shots": 2048}, update_calibration_parameters=True)
    effective = override.effective_settings(defaults)
    assert effective["run"]["shots"] == {"value": 2048}
    assert effective["update_calibration_parameters"] is True


@pytest.mark.parametrize(
    "value",
    [
        sweep.linspace(0, 1, 5),
        sweep.logspace(2, 6, 51),
        sweep.arange(0, 50_001, 500),
        sweep.range(0, 10, 2),
        sweep.values(0, 4, 16),
        {"value": [0, 10, 2], "value_type": "np.arange"},
        3,
        [1, 2, 3],
        {"value": 0.25, "unit": "a.u."},
    ],
)
def test_calls_round_trip_through_json(value: Any) -> None:
    call = TaskCall(name="CheckRamsey", call_id="ramsey_fine", run={"time_range": value})
    encoded = json.loads(call.model_dump_json())
    decoded = TaskCall.model_validate(encoded)
    assert decoded.model_dump(mode="json") == call.model_dump(mode="json")
    # The JSON form is already canonical: decoding it again changes nothing.
    assert TaskCall.model_validate(decoded.model_dump(mode="json")) == decoded


def test_input_overrides_reject_sweeps_and_missing_values() -> None:
    with pytest.raises(ValidationError, match="uses a sweep"):
        TaskCall(name="CheckRabi", input={"control_amplitude": sweep.linspace(0, 1, 3)})
    with pytest.raises(ValidationError, match="needs a value"):
        TaskCall(name="CheckRabi", input={"control_amplitude": None})
    assert TaskCall(name="CheckRabi", input={"control_amplitude": {"value": 0.1}}).input == {
        "control_amplitude": 0.1
    }


def test_task_parameters_are_typed_per_task_defaults() -> None:
    parsed = parse(
        task_parameters={
            "CheckRabi": {"run": {"shots": 512}, "update_calibration_parameters": False}
        }
    )
    assert parsed.canonical_task_parameters() == {
        "CheckRabi": {
            "run": {"shots": {"value": 512}},
            "input": {},
            "update_calibration_parameters": False,
        }
    }
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse(task_parameters={"CheckRabi": {"shots": 512}})
    with pytest.raises(ValidationError, match="task_run_parameters"):
        parse(task_run_parameters={"CheckRabi": {"shots": 512}})


# ---------------------------------------------------------------- references


def test_filters_can_reference_a_custom_steps_call() -> None:
    parsed = parse(
        steps=[
            {"type": "OneQubitCheck"},
            {
                "type": "CustomOneQubit",
                "step_name": "ramsey",
                "tasks": [
                    {"name": "CheckRamsey", "call_id": "coarse"},
                    {"name": "CheckRamsey", "call_id": "fine"},
                ],
            },
            {"type": "FilterByStatus", "step": "ramsey", "call_id": "fine"},
            {
                "type": "FilterByMetric",
                "step": "ramsey",
                "call_id": "fine",
                "metric": "t2_star",
                "threshold": 5.0,
            },
        ]
    )
    assert parsed.plan()["steps"][2]["type"] == "FilterByStatus"


def test_a_custom_step_alone_satisfies_an_explicit_filter() -> None:
    parse(
        steps=[
            {"type": "CustomOneQubit", "step_name": "coh", "tasks": [{"name": "CheckT1"}]},
            {"type": "FilterByStatus", "step": "coh"},
        ]
    )


@pytest.mark.parametrize(
    ("filter_step", "message"),
    [
        ({"type": "FilterByStatus", "step": "later"}, "references step 'later', which is not an"),
        ({"type": "FilterByStatus", "call_id": "fine"}, "without the step it belongs to"),
        (
            {"type": "FilterByStatus", "step": "ramsey", "call_id": "medium"},
            "references call 'medium', which step 'ramsey' does not run",
        ),
        (
            {"type": "FilterByMetric", "step": "ramsey", "metric": "t2_star", "threshold": 1},
            "set call_id to read an output parameter",
        ),
        (
            {"type": "FilterByStatus", "step": "two_qubit_calibration"},
            "without qubit results",
        ),
    ],
)
def test_bad_filter_references_are_rejected(filter_step: dict[str, Any], message: str) -> None:
    steps: list[dict[str, Any]] = [
        {
            "type": "CustomOneQubit",
            "step_name": "ramsey",
            "tasks": [
                {"name": "CheckRamsey", "call_id": "coarse"},
                {"name": "CheckRamsey", "call_id": "fine"},
            ],
        },
        {"type": "GenerateCRSchedule"},
        {"type": "TwoQubitCalibration"},
        filter_step,
        {"type": "CustomOneQubit", "step_name": "later", "tasks": [{"name": "CheckT1"}]},
    ]
    with pytest.raises(ValidationError, match=message):
        parse(steps=steps)


def test_builtin_step_metric_is_read_from_the_step() -> None:
    parse(
        steps=[
            {"type": "OneQubitFineTune", "step_id": "fine"},
            {"type": "FilterByMetric", "step": "fine", "metric": "x90_fidelity", "threshold": 0.9},
        ]
    )


def test_warning_when_a_reference_free_filter_skips_a_custom_step() -> None:
    parsed = parse(
        steps=[
            {"type": "OneQubitCheck"},
            {"type": "CustomOneQubit", "step_name": "ramsey", "tasks": [{"name": "CheckRamsey"}]},
            {"type": "FilterByStatus"},
        ]
    )
    [(path, message)] = pipeline_warnings(parsed)
    assert path == "steps[2]"
    assert "ignores ramsey" in message
    explicit = parse(
        steps=[
            {"type": "OneQubitCheck"},
            {"type": "CustomOneQubit", "step_name": "ramsey", "tasks": [{"name": "CheckRamsey"}]},
            {"type": "FilterByStatus", "step": "ramsey"},
        ]
    )
    assert pipeline_warnings(explicit) == []


def test_deprecated_task_parameters_is_reported_but_still_applied() -> None:
    parsed = parse(
        steps=[
            {
                "type": "CustomOneQubit",
                "tasks": [
                    {"name": "CheckRamsey", "call_id": "coarse"},
                    {
                        "name": "CheckRamsey",
                        "call_id": "fine",
                        "run": {"detuning": 0.0002},
                        "update_calibration_parameters": True,
                    },
                ],
            }
        ],
        task_parameters={
            "CheckRamsey": {
                "run": {"shots": 1024, "detuning": 0.001},
                "input": {"control_amplitude": 0.05},
                "update_calibration_parameters": False,
            }
        },
    )

    [(path, message)] = pipeline_warnings(parsed)
    assert path == "task_parameters"
    assert "deprecated" in message
    assert "CheckRamsey" in message
    defaults = parsed.canonical_task_parameters()
    coarse, fine = (call for _, call in parsed.all_calls())
    assert coarse.effective_settings(defaults) == {
        "run": {"shots": {"value": 1024}, "detuning": {"value": 0.001}},
        "input": {"control_amplitude": 0.05},
        "update_calibration_parameters": False,
    }
    assert fine.effective_settings(defaults) == {
        "run": {"shots": {"value": 1024}, "detuning": {"value": 0.0002}},
        "input": {"control_amplitude": 0.05},
        "update_calibration_parameters": True,
    }


def test_task_call_settings_without_task_parameters_do_not_warn() -> None:
    parsed = parse(
        steps=[
            {
                "type": "CustomOneQubit",
                "tasks": [{"name": "CheckRamsey", "run": {"shots": 1024}}],
            }
        ],
    )

    assert pipeline_warnings(parsed) == []


# ---------------------------------------------------------------- plan and migration


def test_plan_lists_resolved_calls_and_digest_is_stable() -> None:
    parsed = parse(steps=[{"type": "OneQubitCheck", "configure": True}])
    plan = parsed.plan()
    assert plan["steps"][0]["calls"][0] == {"name": "Configure", "call_id": "Configure"}
    assert (
        parsed.plan_digest()
        == parse(steps=[{"type": "OneQubitCheck", "configure": True}]).plan_digest()
    )
    assert parsed.plan_digest() != parse(steps=[{"type": "OneQubitCheck"}]).plan_digest()


@pytest.mark.parametrize("step_type", ["OneQubitCheck", "OneQubitFineTune"])
@pytest.mark.parametrize(
    "tasks",
    [
        [{"name": "Configure"}],
        [{"name": "Configure", "call_id": "explicit"}],
        [{"name": "CheckRabi", "call_id": "Configure"}],
    ],
)
def test_configure_flag_rejects_a_conflicting_call(
    step_type: str, tasks: list[dict[str, Any]]
) -> None:
    # configure=True prepends Configure with call_id "Configure"; a step that
    # also lists Configure, or reuses that id, is a validation problem of the step.
    with pytest.raises(ValidationError, match="configure=True already runs Configure"):
        parse(steps=[{"type": step_type, "configure": True, "tasks": tasks}])
    without_flag = parse(steps=[{"type": step_type, "tasks": tasks}])
    assert [call.resolved_call_id for call in step_calls(without_flag.steps[0])] == [
        task.get("call_id", task["name"]) for task in tasks
    ]


@pytest.mark.parametrize("step_type", ["OneQubitCheck", "OneQubitFineTune"])
def test_configure_flag_prepends_one_configure_call(step_type: str) -> None:
    parsed = parse(steps=[{"type": step_type, "configure": True, "tasks": [{"name": "CheckRabi"}]}])
    assert [(call.name, call.call_id) for _, call in parsed.all_calls()] == [
        ("Configure", "Configure"),
        ("CheckRabi", "CheckRabi"),
    ]


def test_version_1_spec_migrates_without_changing_what_runs() -> None:
    v1 = {
        "name": "legacy",
        "targets": {"qids": ["0"]},
        "steps": [
            {"type": "OneQubitCheck", "tasks": ["CheckRabi", "CreateHPIPulse"]},
            {"type": "FilterByStatus"},
            {"type": "CustomOneQubit", "step_name": "coh", "tasks": ["CheckT1", "CheckT1"]},
        ],
        "task_run_parameters": {
            "CheckT1": {"shots": 512, "update_calibration_parameters": False},
        },
        "default_run_parameters": {"interval": 1024},
    }
    migration = migrate_pipeline_spec(v1)

    assert migration.from_version == 1
    assert migration.changed
    migrated = CalibrationPipelineSpec.model_validate(migration.spec)
    assert migrated.all_tasks() == ["CheckRabi", "CreateHPIPulse", "CheckT1", "CheckT1"]
    assert [call.call_id for call in step_calls(migrated.steps[2])] == ["CheckT1", "CheckT1_2"]
    assert migrated.canonical_task_parameters() == {
        "CheckT1": {
            "run": {"shots": {"value": 512}},
            "input": {},
            "update_calibration_parameters": False,
        }
    }
    assert migrated.default_run_parameters == {"interval": 1024}
    assert any("CheckT1_2" in note for note in migration.notes)
    # The input is not modified, and the conversion is deterministic.
    assert v1["steps"][0]["tasks"] == ["CheckRabi", "CreateHPIPulse"]  # type: ignore[index]
    assert migrate_pipeline_spec(v1).spec == migration.spec


def test_migration_call_ids_skip_ids_the_step_already_uses() -> None:
    v1 = {
        "targets": {"qids": ["0"]},
        "steps": [
            {
                "type": "CustomOneQubit",
                "step_name": "x",
                "tasks": [
                    "CheckT1",
                    "CheckT1",
                    "CheckT1_2",
                    {"name": "CheckRabi", "call_id": "CheckT1_3"},
                ],
            }
        ],
    }
    migration = migrate_pipeline_spec(v1)
    migrated = CalibrationPipelineSpec.model_validate(migration.spec)
    assert [call.call_id for call in step_calls(migrated.steps[0])] == [
        "CheckT1",
        "CheckT1_4",
        "CheckT1_2",
        "CheckT1_3",
    ]
    assert any("CheckT1, CheckT1_4" in note for note in migration.notes)


def test_migration_gives_repeated_builtin_steps_unique_step_ids() -> None:
    v1 = {
        "targets": {"qids": ["0"]},
        "steps": [
            {"type": "OneQubitCheck"},
            {"type": "CustomOneQubit", "step_name": "one_qubit_check_2", "tasks": ["CheckT1"]},
            {"type": "OneQubitCheck", "tasks": ["CheckRabi"]},
            {"type": "FilterByStatus"},
            {"type": "OneQubitCheck"},
            {"type": "FilterByMetric", "metric": "t1_average", "threshold": 0.0},
        ],
    }
    migration = migrate_pipeline_spec(v1)
    migrated = CalibrationPipelineSpec.model_validate(migration.spec)
    assert [step_id(step) for step in migrated.steps] == [
        "one_qubit_check",
        "one_qubit_check_2",
        "one_qubit_check_3",
        None,
        "one_qubit_check_4",
        None,
    ]
    # Filters keep reading the latest built-in one-qubit step, as in version 1.
    assert migrated.steps[3].step is None  # type: ignore[union-attr]
    assert sum("assigned step_id" in note for note in migration.notes) == 2
    assert migrate_pipeline_spec(v1).spec == migration.spec


def test_migration_keeps_unique_builtin_steps_on_their_default_ids() -> None:
    v1 = {
        "targets": {"qids": ["0"]},
        "steps": [{"type": "OneQubitCheck"}, {"type": "OneQubitFineTune"}],
    }
    migration = migrate_pipeline_spec(v1)
    assert all("step_id" not in step for step in migration.spec["steps"])
    assert migration.notes == []


def test_version_2_spec_is_returned_unchanged() -> None:
    current = spec()
    migration = migrate_pipeline_spec(current)
    assert migration.from_version == 2
    assert not migration.changed
    assert migration.spec == current


def test_unknown_spec_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown spec_version 3"):
        migrate_pipeline_spec({"spec_version": 3})


def test_json_schema_lists_every_step_type_and_task_call() -> None:
    schema = pipeline_spec_json_schema()
    defs = schema["$defs"]
    for step_type in STEP_CATALOG:
        assert f"{step_type}Step" in defs, step_type
    assert "TaskCall" in defs
    assert defs["TaskCall"]["additionalProperties"] is False
    assert schema["required"] == ["spec_version", "targets", "steps"]
    # task_parameters is deprecated in the schema but stays optional and accepted.
    assert schema["properties"]["task_parameters"]["deprecated"] is True
    assert schema["properties"]["task_parameters"]["description"].startswith("Deprecated")


def test_configure_all_step_runs_the_default_call_without_changing_its_digest() -> None:
    parsed = parse(targets={"mux_ids": [0]}, steps=[{"type": "ConfigureAll"}])
    assert step_calls(parsed.steps[0]) == [TaskCall(name="ConfigureAll", call_id="ConfigureAll")]
    assert parsed.all_tasks() == ["ConfigureAll"]
    assert parsed.plan()["steps"][0]["calls"] == [
        {"name": "ConfigureAll", "call_id": "ConfigureAll"}
    ]
    # An unset call is left out of the dump, so existing specs keep their plan digest.
    assert "call" not in parsed.model_dump(mode="json")["steps"][0]


def test_configure_all_step_call_carries_configuration_mode() -> None:
    call = {"name": "ConfigureAll", "run": {"configuration_mode": "ge-ef-cr"}}
    default = parse(targets={"mux_ids": [0]}, steps=[{"type": "ConfigureAll"}])
    parsed = parse(targets={"mux_ids": [0]}, steps=[{"type": "ConfigureAll", "call": call}])
    assert step_calls(parsed.steps[0]) == [
        TaskCall(
            name="ConfigureAll",
            call_id="ConfigureAll",
            run={"configuration_mode": "ge-ef-cr"},
        )
    ]
    assert parsed.plan()["steps"][0]["calls"] == [
        {
            "name": "ConfigureAll",
            "call_id": "ConfigureAll",
            "run": {"configuration_mode": {"value": "ge-ef-cr"}},
        }
    ]
    assert parsed.plan_digest() != default.plan_digest()
    assert pipeline_warnings(parsed) == []


@pytest.mark.parametrize(
    ("call", "message"),
    [
        ({"name": "Configure"}, "must name ConfigureAll, got 'Configure'"),
        ({"name": "ConfigureAll", "nonsense": 1}, "Extra inputs are not permitted"),
        ("ConfigureAll", "valid dictionary or instance of TaskCall"),
    ],
)
def test_configure_all_step_rejects_invalid_calls(call: Any, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        parse(targets={"mux_ids": [0]}, steps=[{"type": "ConfigureAll", "call": call}])


def test_configure_all_mux_ids_settings_warn_that_the_step_replaces_them() -> None:
    parsed = parse(
        targets={"mux_ids": [0]},
        steps=[{"type": "ConfigureAll", "call": {"name": "ConfigureAll", "run": {"mux_ids": [5]}}}],
        task_parameters={"ConfigureAll": {"run": {"mux_ids": [6]}}},
    )
    warned = dict(pipeline_warnings(parsed))
    assert "replaces this value" in warned["steps[0].call.run.mux_ids"]
    assert "replaces this value" in warned["task_parameters.ConfigureAll.run.mux_ids"]
