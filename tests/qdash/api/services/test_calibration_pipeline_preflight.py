"""Tests for the plan-time preflight checks of a calibration pipeline spec."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qdash.api.schemas.task_file import TaskInfo
from qdash.api.services.calibration_pipeline_preflight import (
    PreflightTask,
    batch_input_problems,
    effective_readout_duration,
    input_parameter_problems,
    prerequisite_problems,
    run_parameter_problems,
)
from qdash.common.config.calibration import DEFAULT_READOUT_DURATION
from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec

RABI_INPUTS = {
    name: {"resolution": "database_required", "parameter_name": name, "qid_role": "self"}
    for name in (
        "rabi_amplitude",
        "maximum_rabi_frequency",
        "control_amplitude",
        "rabi_phase",
        "rabi_offset",
        "rabi_angle",
        "rabi_noise",
        "rabi_distance",
        "rabi_reference_phase",
        "rabi_r2",
    )
}
RABI_OUTPUTS = tuple(RABI_INPUTS)
COMMON_RUN = {
    "readout_duration": {"value_type": "float", "value": DEFAULT_READOUT_DURATION},
    "shots": {"value_type": "int", "value": 1024},
    "interval": {"value_type": "int", "value": 153600},
}

TASKS = {
    "CheckRabi": PreflightTask(
        name="CheckRabi",
        input_parameters={
            "control_frequency": {
                "resolution": "database_required",
                "fallback_parameter_names": ["qubit_frequency"],
            },
            "readout_frequency": {
                "resolution": "database_required",
                "fallback_parameter_names": ["resonator_frequency"],
            },
            "readout_amplitude": {"resolution": "database_or_default", "default_value": 0.01},
        },
        run_parameters={**COMMON_RUN, "time_range": {"value_type": "range", "value": [0, 201, 4]}},
        output_parameters=RABI_OUTPUTS,
    ),
    "CreateHPIPulse": PreflightTask(
        name="CreateHPIPulse",
        input_parameters=RABI_INPUTS,
        run_parameters=COMMON_RUN,
        output_parameters=("hpi_amplitude", "hpi_duration"),
    ),
    "CreatePIPulse": PreflightTask(
        name="CreatePIPulse",
        input_parameters=RABI_INPUTS,
        run_parameters=COMMON_RUN,
        output_parameters=("pi_amplitude", "pi_duration"),
    ),
    "CheckT1": PreflightTask(
        name="CheckT1",
        input_parameters={
            **RABI_INPUTS,
            "hpi_amplitude": {"resolution": "database_required"},
            "readout_amplitude": {"resolution": "database_required"},
        },
        run_parameters={
            **COMMON_RUN,
            "time_range": {"value_type": "np.logspace", "value": [3, 5, 51]},
        },
        output_parameters=("t1",),
    ),
    "CheckCrossResonance": PreflightTask(
        name="CheckCrossResonance",
        input_parameters={
            "control_rabi_amplitude": {
                "resolution": "database_required",
                "parameter_name": "rabi_amplitude",
                "qid_role": "control",
            },
        },
        run_parameters=COMMON_RUN,
        output_parameters=("cr_amplitude",),
    ),
}

CALIBRATED = {
    "qubit_frequency": {"value": 7.5},
    "resonator_frequency": {"value": 10.1},
    "readout_amplitude": {"value": 0.02},
    "hpi_amplitude": {"value": 0.3},
    **{name: {"value": 1.0, "task_id": "rabi-task"} for name in RABI_INPUTS},
}


def spec(
    steps: list[dict[str, Any]],
    *,
    qids: tuple[str, ...] = ("0", "1"),
    **extra: Any,
) -> CalibrationPipelineSpec:
    return CalibrationPipelineSpec.model_validate(
        {"spec_version": 2, "targets": {"qids": list(qids)}, "steps": steps, **extra}
    )


def one_qubit_check() -> dict[str, Any]:
    return {"type": "OneQubitCheck"}


def custom(*tasks: str | dict[str, Any], step_name: str = "custom") -> dict[str, Any]:
    calls = [{"name": task} if isinstance(task, str) else task for task in tasks]
    return {"type": "CustomOneQubit", "step_name": step_name, "tasks": calls}


def paths(problems: list[Any]) -> dict[str, str]:
    return {problem.path: problem.message for problem in problems}


# --------------------------------------------------------------------- run parameters


def test_effective_readout_duration_defaults_to_the_task_default() -> None:
    assert effective_readout_duration(spec([custom("CheckT1")])) == float(DEFAULT_READOUT_DURATION)
    shared = spec([custom("CheckT1")], default_run_parameters={"readout_duration": 384})
    assert effective_readout_duration(shared) == 384.0
    bad = spec([custom("CheckT1")], default_run_parameters={"readout_duration": 0})
    assert effective_readout_duration(bad) is None


def test_valid_run_parameters_have_no_problems() -> None:
    valid = spec(
        [one_qubit_check(), custom("CheckT1")],
        task_parameters={
            "CheckT1": {
                "run": {
                    "shots": 2048,
                    "time_range": {"value": [0, 500, 26], "value_type": "np.linspace"},
                    "readout_duration": DEFAULT_READOUT_DURATION,
                }
            }
        },
        default_run_parameters={"shots": 512, "readout_duration": {"value": None}},
    )
    assert run_parameter_problems(valid, TASKS) == []


def test_undeclared_and_mistyped_task_run_parameters_are_problems() -> None:
    bad = spec(
        [custom("CheckT1")],
        task_parameters={
            "CheckT1": {"run": {"n_shots": 10, "shots": "many", "time_range": 5}},
            "NoSuchTask": {"run": {"shots": 1}},
        },
    )
    problems = paths(run_parameter_problems(bad, TASKS))
    assert (
        "does not declare run parameter 'n_shots'"
        in problems["task_parameters.CheckT1.run.n_shots"]
    )
    assert "must be int" in problems["task_parameters.CheckT1.run.shots"]
    assert "must be np.logspace" in problems["task_parameters.CheckT1.run.time_range"]
    # An unknown task is reported by the task check, not here.
    assert "task_parameters.NoSuchTask.run.shots" not in problems


def test_call_run_values_are_checked_with_paths_into_the_call() -> None:
    bad = spec(
        [
            custom(
                {"name": "CheckT1", "call_id": "t1_short", "run": {"shots": 512}},
                {"name": "CheckT1", "call_id": "t1_long", "run": {"shots": "many"}},
                {"name": "CheckRabi", "run": {"readout_amplitude": 0.1}},
            )
        ]
    )
    problems = paths(run_parameter_problems(bad, TASKS))
    assert set(problems) == {
        "steps[0].tasks[1].run.shots",
        "steps[0].tasks[2].run.readout_amplitude",
    }
    assert "must be int" in problems["steps[0].tasks[1].run.shots"]
    assert "set it under input" in problems["steps[0].tasks[2].run.readout_amplitude"]


def test_call_and_default_input_names_must_be_declared() -> None:
    bad = spec(
        [
            custom(
                {"name": "CheckRabi", "input": {"readout_amplitude": 0.05, "shots": 3}},
                {"name": "CheckT1", "input": {"nonsense": 1.0}},
            )
        ],
        task_parameters={"CheckRabi": {"input": {"control_frequency": 7.0}}},
    )
    problems = paths(input_parameter_problems(bad, TASKS))
    assert set(problems) == {
        "steps[0].tasks[0].input.shots",
        "steps[0].tasks[1].input.nonsense",
    }
    assert "run parameter" in problems["steps[0].tasks[0].input.shots"]


def test_batch_mode_rejects_input_overrides_before_dispatch() -> None:
    batch = spec(
        [
            {
                "type": "CustomOneQubit",
                "step_name": "spectroscopy",
                "mode": "simultaneous_spectroscopy",
                "tasks": [
                    {"name": "CheckRabi", "call_id": "first"},
                    {"name": "CheckRabi", "call_id": "second", "input": {"readout_amplitude": 1}},
                ],
            }
        ],
    )
    problems = paths(batch_input_problems(batch))
    assert list(problems) == ["steps[0].tasks[1]"]
    assert "simultaneous_spectroscopy" in problems["steps[0].tasks[1]"]
    defaults = spec(
        [{"type": "OneQubitCheck", "mode": "simultaneous_spectroscopy"}],
        task_parameters={"CheckRabi": {"input": {"readout_amplitude": 1}}},
    )
    assert list(paths(batch_input_problems(defaults))) == ["steps[0]"]
    serial = spec(
        [{"type": "OneQubitCheck", "mode": "serial"}],
        task_parameters={"CheckRabi": {"input": {"readout_amplitude": 1}}},
    )
    assert batch_input_problems(serial) == []


def test_shared_run_parameters_are_checked_against_every_declaring_task() -> None:
    bad = spec(
        [one_qubit_check(), custom("CheckT1")],
        default_run_parameters={
            "shots": {"value": [1, 2, 3], "value_type": "np.linspace"},
            "n_shots": 100,
            "readout_duration": -1,
        },
    )
    problems = run_parameter_problems(bad, TASKS)
    by_path: dict[str, list[str]] = {}
    for problem in problems:
        by_path.setdefault(problem.path, []).append(problem.message)
    # CheckRabi, CreateHPIPulse, CreatePIPulse, CheckT1
    assert len(by_path["default_run_parameters.shots"]) == 4
    assert all("cannot take np.linspace" in m for m in by_path["default_run_parameters.shots"])
    assert "would be ignored" in by_path["default_run_parameters.n_shots"][0]
    assert "finite positive" in by_path["default_run_parameters.readout_duration"][0]


def test_shared_parameter_unknown_to_some_task_is_fine() -> None:
    # Only CheckRabi declares time_range as a range; CheckT1 declares a logspace.
    mixed = spec(
        [one_qubit_check(), custom("CheckT1")],
        default_run_parameters={"time_range": {"value": [0, 201, 4], "value_type": "range"}},
    )
    problems = paths(run_parameter_problems(mixed, TASKS))
    assert problems == {}


def test_per_task_readout_duration_must_match_the_session() -> None:
    mismatched = spec(
        [custom("CheckT1")],
        task_parameters={"CheckT1": {"run": {"readout_duration": 2048}}},
    )
    problems = paths(run_parameter_problems(mismatched, TASKS))
    message = problems["task_parameters.CheckT1.run.readout_duration"]
    assert "session-scoped" in message
    assert "2048 ns" in message
    assert f"{DEFAULT_READOUT_DURATION} ns" in message

    aligned = spec(
        [custom("CheckT1")],
        task_parameters={"CheckT1": {"run": {"readout_duration": 2048}}},
        default_run_parameters={"readout_duration": 2048},
    )
    assert run_parameter_problems(aligned, TASKS) == []


def test_tasks_without_metadata_are_skipped() -> None:
    unknown = spec(
        [custom("CheckT1", "Mystery")],
        task_parameters={"Mystery": {"run": {"anything": 1}}},
        default_run_parameters={"shots": 1},
    )
    assert run_parameter_problems(unknown, TASKS) == []


# ---------------------------------------------------------------------- prerequisites


def calibrated_lookup(**per_qid: dict[str, Any]) -> Any:
    def lookup(qid: str) -> dict[str, Any]:
        return per_qid.get(qid, CALIBRATED)

    return lookup


def source_lookup(**by_task: dict[str, Any] | None) -> Any:
    def lookup(task_id: str) -> dict[str, Any] | None:
        return by_task.get(task_id)

    return lookup


RABI_SOURCE = {"readout_duration": {"value": DEFAULT_READOUT_DURATION, "value_type": "float"}}


def test_calibrated_chip_has_no_prerequisite_problems() -> None:
    pipeline = spec([one_qubit_check(), custom("CheckT1")])
    problems = prerequisite_problems(
        pipeline,
        ["0", "1"],
        TASKS,
        calibrated_lookup(),
        source_lookup(**{"rabi-task": RABI_SOURCE}),
    )
    assert problems == []


def test_missing_required_inputs_name_the_parameter_and_qubits() -> None:
    pipeline = spec([custom("CheckT1")])
    problems = prerequisite_problems(
        pipeline,
        ["0", "1", "2"],
        TASKS,
        calibrated_lookup(**{"1": {}, "2": {"readout_amplitude": {"value": 0.01}}}),
        None,
    )
    messages = [p.message for p in problems]
    assert all(p.path == "steps[0].tasks[0]" for p in problems)
    rabi = next(m for m in messages if "'rabi_amplitude'" in m)
    assert "qubit(s) 1, 2" in rabi
    amplitude = next(m for m in messages if "'readout_amplitude'" in m)
    assert "qubit(s) 1" in amplitude
    assert "no earlier task in this pipeline writes it" in amplitude


def test_inputs_written_earlier_in_the_pipeline_are_satisfied() -> None:
    # CheckRabi writes the Rabi set and CreateHPIPulse writes hpi_amplitude, so an
    # uncalibrated qubit only lacks what no task in the pipeline produces.
    pipeline = spec([one_qubit_check(), custom("CheckT1")])
    bare = {"qubit_frequency": {"value": 7.5}, "resonator_frequency": {"value": 10.1}}
    problems = prerequisite_problems(pipeline, ["0"], TASKS, calibrated_lookup(**{"0": bare}), None)
    assert [p.path for p in problems] == ["steps[1].tasks[0]"]
    assert "'readout_amplitude'" in problems[0].message


def test_fallback_names_satisfy_a_required_input() -> None:
    pipeline = spec([custom("CheckRabi")])
    data = {"control_frequency": {"value": 7.5}, "readout_frequency": {"value": 10.1}}
    assert (
        prerequisite_problems(pipeline, ["0"], TASKS, calibrated_lookup(**{"0": data}), None) == []
    )
    entry_without_value = {
        "qubit_frequency": {"unit": "GHz"},
        "resonator_frequency": {"value": 10.1},
    }
    problems = prerequisite_problems(
        pipeline, ["0"], TASKS, calibrated_lookup(**{"0": entry_without_value}), None
    )
    assert len(problems) == 1
    assert "'control_frequency'" in problems[0].message


def test_restored_rabi_parameters_must_match_the_session_readout_duration() -> None:
    pipeline = spec([custom("CheckT1")])
    sources = source_lookup(
        **{"rabi-task": {"readout_duration": {"value": 384.0, "value_type": "float"}}}
    )
    problems = prerequisite_problems(pipeline, ["0", "1"], TASKS, calibrated_lookup(), sources)
    assert len(problems) == 1
    message = problems[0].message
    assert "384 ns" in message
    assert f"{DEFAULT_READOUT_DURATION} ns" in message
    assert "qubit(s) 0, 1" in message
    assert "default_run_parameters.readout_duration to 384" in message

    aligned = spec([custom("CheckT1")], default_run_parameters={"readout_duration": 384})
    assert prerequisite_problems(aligned, ["0", "1"], TASKS, calibrated_lookup(), sources) == []


def test_rabi_parameters_without_a_recorded_source_are_a_problem() -> None:
    pipeline = spec([custom("CheckT1")])
    no_task_id = {**CALIBRATED, "rabi_amplitude": {"value": 1.0}}
    problems = prerequisite_problems(
        pipeline,
        ["0", "1"],
        TASKS,
        calibrated_lookup(**{"0": no_task_id}),
        source_lookup(),  # qubit 1 points at a task the history does not have
    )
    assert len(problems) == 1
    assert "source readout_duration is not recorded" in problems[0].message
    assert "qubit(s) 0, 1" in problems[0].message


def test_rabi_check_is_skipped_when_check_rabi_runs_earlier() -> None:
    pipeline = spec([one_qubit_check(), custom("CheckT1")])
    stale = source_lookup(**{"rabi-task": {"readout_duration": {"value": 384.0}}})
    assert prerequisite_problems(pipeline, ["0"], TASKS, calibrated_lookup(), stale) == []


def test_coupling_steps_and_unknown_tasks_are_not_checked() -> None:
    pipeline = spec(
        [
            custom("Mystery"),
            {
                "type": "CustomTwoQubit",
                "step_name": "cr",
                "tasks": [{"name": "CheckCrossResonance"}],
            },
        ]
    )
    assert prerequisite_problems(pipeline, ["0"], TASKS, calibrated_lookup(**{"0": {}}), None) == []


def test_no_target_qubits_means_no_prerequisite_problems() -> None:
    assert (
        prerequisite_problems(spec([custom("CheckT1")]), [], TASKS, calibrated_lookup(), None) == []
    )


# ------------------------------------------------- persistence policy of earlier calls

TASK_CATALOG_PATH = (
    Path(__file__).resolve().parents[4] / "src/qdash/workflow/calibtasks/task_catalog.json"
)


def catalog_tasks(*names: str) -> dict[str, PreflightTask]:
    """Task metadata as the API serves it, from the generated qubex catalog."""
    catalog = json.loads(TASK_CATALOG_PATH.read_text(encoding="utf-8"))
    infos = {task["name"]: task for task in catalog["backends"]["qubex"]}
    return {
        name: PreflightTask.from_task_info(TaskInfo.model_validate(infos[name])) for name in names
    }


# A qubit that has spectroscopy results but has never had CheckRabi persisted.
NO_RABI = {
    "qubit_frequency": {"value": 7.5},
    "resonator_frequency": {"value": 10.1},
    "readout_amplitude": {"value": 0.02},
}


def rabi_problems(steps: list[dict[str, Any]], **extra: Any) -> list[Any]:
    return prerequisite_problems(
        spec(steps, qids=("0",), **extra),
        ["0"],
        catalog_tasks("CheckRabi", "CreateHPIPulse"),
        calibrated_lookup(**{"0": NO_RABI}),
        None,
    )


def missing_parameters(problems: list[Any]) -> set[str]:
    return {
        problem.message.split("'")[3]
        for problem in problems
        if "needs calibrated" in problem.message
    }


def test_history_only_call_does_not_satisfy_later_inputs() -> None:
    omitted = rabi_problems([custom("CreateHPIPulse")])
    history_only = rabi_problems(
        [custom({"name": "CheckRabi", "update_calibration_parameters": False}, "CreateHPIPulse")]
    )
    assert "rabi_amplitude" in missing_parameters(omitted)
    assert missing_parameters(history_only) == missing_parameters(omitted)
    assert {problem.path for problem in history_only} == {"steps[0].tasks[1]"}

    persisted = rabi_problems([custom("CheckRabi", "CreateHPIPulse")])
    assert persisted == []


def test_call_persistence_setting_overrides_the_task_default() -> None:
    no_update = {"CheckRabi": {"update_calibration_parameters": False}}
    defaulted = rabi_problems([custom("CheckRabi", "CreateHPIPulse")], task_parameters=no_update)
    assert "rabi_amplitude" in missing_parameters(defaulted)

    forced = rabi_problems(
        [custom({"name": "CheckRabi", "update_calibration_parameters": True}, "CreateHPIPulse")],
        task_parameters=no_update,
    )
    assert forced == []


def test_repeated_calls_count_only_the_persisting_one() -> None:
    steps = [
        custom(
            {"name": "CheckRabi", "call_id": "rabi_probe", "update_calibration_parameters": False},
            {"name": "CreateHPIPulse", "call_id": "hpi_early"},
            {"name": "CheckRabi", "call_id": "rabi"},
            {"name": "CreateHPIPulse", "call_id": "hpi"},
        )
    ]
    problems = rabi_problems(steps)
    assert {problem.path for problem in problems} == {"steps[0].tasks[1]"}


def test_input_overrides_do_not_satisfy_database_required_inputs() -> None:
    # The task loads database-required inputs before it applies overrides.
    problems = rabi_problems([custom({"name": "CreateHPIPulse", "input": {"rabi_amplitude": 0.1}})])
    assert "rabi_amplitude" in missing_parameters(problems)


def test_history_only_check_rabi_keeps_the_persisted_rabi_provenance_check() -> None:
    pipeline = spec(
        [custom({"name": "CheckRabi", "update_calibration_parameters": False}, "CheckT1")]
    )
    stale = source_lookup(**{"rabi-task": {"readout_duration": {"value": 384.0}}})
    problems = prerequisite_problems(pipeline, ["0"], TASKS, calibrated_lookup(), stale)
    assert [problem.path for problem in problems] == ["steps[0].tasks[1]"]
    assert "384 ns" in problems[0].message


def test_problem_paths_skip_the_implicit_configure_call() -> None:
    pipeline = spec([{"type": "OneQubitCheck", "configure": True, "tasks": [{"name": "CheckT1"}]}])
    problems = prerequisite_problems(pipeline, ["0"], TASKS, calibrated_lookup(**{"0": {}}), None)
    assert problems
    assert {problem.path for problem in problems} == {"steps[0].tasks[0]"}


CONFIGURE_ALL_TASKS = {
    **TASKS,
    "ConfigureAll": PreflightTask(
        name="ConfigureAll",
        input_parameters={},
        run_parameters={
            "configuration_mode": {"value_type": "str", "value": "ge-cr-cr"},
            "mux_ids": {"value_type": "list", "value": []},
        },
        output_parameters=(),
    ),
}


def test_configure_all_call_settings_are_checked_with_paths_into_the_call() -> None:
    pipeline = spec(
        [
            {
                "type": "ConfigureAll",
                "call": {
                    "name": "ConfigureAll",
                    "run": {"configuration_mode": 3, "shots": 10},
                    "input": {"control_frequency": 7.0},
                },
            },
            custom({"name": "CheckT1", "run": {"shots": "many"}}),
        ]
    )
    run_problems = paths(run_parameter_problems(pipeline, CONFIGURE_ALL_TASKS))
    assert set(run_problems) == {
        "steps[0].call.run.configuration_mode",
        "steps[0].call.run.shots",
        "steps[1].tasks[0].run.shots",
    }
    assert "must be str" in run_problems["steps[0].call.run.configuration_mode"]
    input_problems = paths(input_parameter_problems(pipeline, CONFIGURE_ALL_TASKS))
    assert set(input_problems) == {"steps[0].call.input.control_frequency"}


def test_valid_configure_all_call_has_no_problems() -> None:
    pipeline = spec(
        [
            {
                "type": "ConfigureAll",
                "call": {"name": "ConfigureAll", "run": {"configuration_mode": "ge-ef-cr"}},
            },
            {"type": "ConfigureAll", "step_id": "configure_all_default"},
        ]
    )
    assert run_parameter_problems(pipeline, CONFIGURE_ALL_TASKS) == []
    assert input_parameter_problems(pipeline, CONFIGURE_ALL_TASKS) == []
    assert batch_input_problems(pipeline) == []
    assert prerequisite_problems(pipeline, ["0"], CONFIGURE_ALL_TASKS, lambda _qid: {}) == []
