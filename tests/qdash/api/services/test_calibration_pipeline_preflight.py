"""Tests for the plan-time preflight checks of a calibration pipeline spec."""

from __future__ import annotations

from typing import Any

from qdash.api.services.calibration_pipeline_preflight import (
    PreflightTask,
    effective_readout_duration,
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
        {"targets": {"qids": list(qids)}, "steps": steps, **extra}
    )


def one_qubit_check() -> dict[str, Any]:
    return {"type": "OneQubitCheck"}


def custom(*tasks: str, step_name: str = "custom") -> dict[str, Any]:
    return {"type": "CustomOneQubit", "step_name": step_name, "tasks": list(tasks)}


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
        task_run_parameters={
            "CheckT1": {
                "shots": 2048,
                "time_range": {"value": [0, 500, 26], "value_type": "np.linspace"},
                "readout_duration": DEFAULT_READOUT_DURATION,
            }
        },
        default_run_parameters={"shots": 512, "readout_duration": {"value": None}},
    )
    assert run_parameter_problems(valid, TASKS) == []


def test_undeclared_and_mistyped_task_run_parameters_are_problems() -> None:
    bad = spec(
        [custom("CheckT1")],
        task_run_parameters={
            "CheckT1": {"n_shots": 10, "shots": "many", "time_range": 5},
            "NoSuchTask": {"shots": 1},
        },
    )
    problems = paths(run_parameter_problems(bad, TASKS))
    assert (
        "does not declare run parameter 'n_shots'"
        in problems["task_run_parameters.CheckT1.n_shots"]
    )
    assert "must be int" in problems["task_run_parameters.CheckT1.shots"]
    assert "must be np.logspace" in problems["task_run_parameters.CheckT1.time_range"]
    # An unknown task is reported by the task check, not here.
    assert "task_run_parameters.NoSuchTask.shots" not in problems


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
        task_run_parameters={"CheckT1": {"readout_duration": 2048}},
    )
    problems = paths(run_parameter_problems(mismatched, TASKS))
    message = problems["task_run_parameters.CheckT1.readout_duration"]
    assert "session-scoped" in message
    assert "2048 ns" in message
    assert f"{DEFAULT_READOUT_DURATION} ns" in message

    aligned = spec(
        [custom("CheckT1")],
        task_run_parameters={"CheckT1": {"readout_duration": 2048}},
        default_run_parameters={"readout_duration": 2048},
    )
    assert run_parameter_problems(aligned, TASKS) == []


def test_tasks_without_metadata_are_skipped() -> None:
    unknown = spec(
        [custom("CheckT1", "Mystery")],
        task_run_parameters={"Mystery": {"anything": 1}},
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
            {"type": "CustomTwoQubit", "step_name": "cr", "tasks": ["CheckCrossResonance"]},
        ]
    )
    assert prerequisite_problems(pipeline, ["0"], TASKS, calibrated_lookup(**{"0": {}}), None) == []


def test_no_target_qubits_means_no_prerequisite_problems() -> None:
    assert (
        prerequisite_problems(spec([custom("CheckT1")]), [], TASKS, calibrated_lookup(), None) == []
    )


# --------------------------------------------------------------------------- #
# Configuration tree checks
# --------------------------------------------------------------------------- #


def _catalog(root: Any) -> Any:
    from qdash.common.config.qubex_layout import QubexLayout
    from qdash.common.config.system_catalog import SystemCatalog

    return SystemCatalog(QubexLayout.detect(root), "src16")


def test_configuration_problems_report_targets_that_span_systems(tmp_path: Any) -> None:
    from qdash.api.services.calibration_pipeline_preflight import configuration_problems
    from tests.qdash.api.services.chip._trees import write_shared_tree

    write_shared_tree(tmp_path)

    same = configuration_problems(_catalog(tmp_path), "src16", ["0", "5"])
    split = configuration_problems(_catalog(tmp_path), "src16", ["0", "9"])

    assert same == []
    assert [p.path for p in split] == ["targets"]
    assert "src16: 0" in split[0].message and "src16-quel3: 9" in split[0].message
    assert "separate pipelines" in split[0].message


def test_configuration_problems_report_missing_boxes_and_unwired_muxes(tmp_path: Any) -> None:
    from qdash.api.services.calibration_pipeline_preflight import configuration_problems
    from tests.qdash.api.services.chip._trees import write_shared_tree

    write_shared_tree(tmp_path, n_qubits=32)  # MUX 4-7 exist but are not wired
    (tmp_path / "config" / "box.yaml").write_text("BOXA:\n  name: a\n  type: quel1se-riken8\n")

    problems = configuration_problems(_catalog(tmp_path), "src16", ["1", "20"])

    messages = [(p.path, p.message) for p in problems]
    assert len(messages) == 2
    assert messages[0][0] == "chip_id" and "missing from box.yaml: q3" in messages[0][1]
    assert messages[1][0] == "targets" and "20" in messages[1][1] and "not wired" in messages[1][1]


def test_configuration_problems_report_an_unreadable_tree(tmp_path: Any) -> None:
    from qdash.api.services.calibration_pipeline_preflight import configuration_problems
    from tests.qdash.api.services.chip._trees import write_shared_tree

    write_shared_tree(tmp_path)
    (tmp_path / "config" / "wiring.yaml").write_text("- not: a mapping\n")

    problems = configuration_problems(_catalog(tmp_path), "src16", ["0"])

    assert [p.path for p in problems] == ["chip_id"]
    assert "could not be read" in problems[0].message


def test_default_system_catalog_skips_chips_without_a_tree(tmp_path: Any, monkeypatch: Any) -> None:
    from qdash.api.services.calibration_pipeline_preflight import default_system_catalog
    from qdash.common.config.qubex_layout import QubexLayout
    from tests.qdash.api.services.chip._trees import write_shared_tree

    monkeypatch.setattr(
        QubexLayout, "detect", classmethod(lambda cls, root=None: _detect(tmp_path))
    )

    assert default_system_catalog("64Qv3") is None
    write_shared_tree(tmp_path)
    catalog = default_system_catalog("src16")
    assert catalog is not None and catalog.system_ids() == ["src16", "src16-quel3"]


def _detect(root: Any) -> Any:
    from qdash.common.config.qubex_layout import QubexLayout, detect_layout_kind

    return QubexLayout(root, detect_layout_kind(root))


def test_configuration_problems_report_schema_violations(tmp_path: Any) -> None:
    from qdash.api.services.calibration_pipeline_preflight import configuration_problems
    from tests.qdash.api.services.chip._trees import write_shared_tree

    write_shared_tree(tmp_path)
    chip_yaml = tmp_path / "config" / "chip.yaml"
    chip_yaml.write_text(chip_yaml.read_text().replace("n_qubits: 16", "n_qubits: sixteen"))

    problems = configuration_problems(_catalog(tmp_path), "src16", ["0"])

    assert [p.path for p in problems] == ["chip_id"]
    assert "config/chip.yaml at src16/n_qubits" in problems[0].message
