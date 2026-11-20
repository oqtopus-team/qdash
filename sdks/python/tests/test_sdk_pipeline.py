"""Pipeline definitions in qdash.sdk.pipeline and the spec JSON they serialize to."""

from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from qdash.client.services.models import CalibrationPipelineSpec, OneQubitCheckStep
from qdash.sdk.pipeline import CustomOneQubit, Pipeline, Qubits, TaskCall, sweep, to_spec

TIME_RANGE = sweep.logspace(math.log10(300), math.log10(500_000), 51)


def coherence_pipeline() -> Pipeline:
    return Pipeline(
        name="coherence-t1-t2echo",
        targets=Qubits(["0", "1"]),
        steps=[
            CustomOneQubit(
                step_name="coherence",
                tasks=[
                    TaskCall(name="Configure"),
                    TaskCall(name="CheckT1", run={"time_range": TIME_RANGE}),
                    TaskCall(name="CheckT2Echo", run={"time_range": TIME_RANGE}),
                ],
            ),
        ],
        default_run_parameters={"readout_duration": 1024, "interval": 262_144},
    )


def test_example_serializes_to_spec_version_2() -> None:
    time_range = {
        "value": [math.log10(300), math.log10(500_000), 51],
        "value_type": "np.logspace",
    }
    assert coherence_pipeline().to_spec() == {
        "spec_version": 2,
        "name": "coherence-t1-t2echo",
        "targets": {"qids": ["0", "1"]},
        "steps": [
            {
                "type": "CustomOneQubit",
                "step_name": "coherence",
                "tasks": [
                    {"name": "Configure"},
                    {"name": "CheckT1", "run": {"time_range": time_range}},
                    {"name": "CheckT2Echo", "run": {"time_range": time_range}},
                ],
            }
        ],
        "default_run_parameters": {"readout_duration": 1024, "interval": 262144},
    }


def test_spec_parses_back_into_the_generated_model() -> None:
    spec = coherence_pipeline().to_spec()

    assert (
        CalibrationPipelineSpec.model_validate(spec).model_dump(mode="json", exclude_unset=True)
        == spec
    )


def test_call_order_and_explicit_call_ids_are_kept() -> None:
    pipeline = Pipeline(
        targets=Qubits(["3"]),
        steps=[
            CustomOneQubit(
                step_name="ramsey",
                execution_mode="sequential",
                continue_on_failure=True,
                tasks=[
                    TaskCall(name="CheckRamsey", call_id="ramsey_fine", on_failure="stop"),
                    TaskCall(name="CheckRamsey", call_id="ramsey_coarse"),
                ],
            )
        ],
    )

    step = pipeline.to_spec()["steps"][0]

    assert [call["call_id"] for call in step["tasks"]] == ["ramsey_fine", "ramsey_coarse"]
    assert step["tasks"][0]["on_failure"] == "stop"
    assert step["execution_mode"] == "sequential"
    assert step["continue_on_failure"] is True


def test_unset_server_defaults_are_left_out() -> None:
    spec = coherence_pipeline().to_spec()

    assert "execution_mode" not in spec["steps"][0]
    assert "tags" not in spec
    assert "task_parameters" not in spec


def test_generated_step_models_and_dict_steps_are_accepted() -> None:
    pipeline = Pipeline(
        targets={"mux_ids": [0], "exclude_qids": ["2"]},
        steps=[
            OneQubitCheckStep.model_validate(
                {"type": "OneQubitCheck", "execution_mode": "parallel_by_mux"}
            ),
            {"type": "FilterByStatus"},
        ],
    )

    spec = pipeline.to_spec()

    assert spec["targets"] == {"mux_ids": [0], "exclude_qids": ["2"]}
    assert spec["steps"] == [
        {"type": "OneQubitCheck", "execution_mode": "parallel_by_mux"},
        {"type": "FilterByStatus"},
    ]


def test_a_mapping_spec_is_passed_through_unchanged() -> None:
    legacy: dict[str, Any] = {
        "spec_version": 1,
        "targets": {"qids": ["0"]},
        "steps": [{"type": "OneQubitCheck", "tasks": ["CheckRabi"]}],
    }

    assert to_spec(legacy) == legacy
    assert to_spec(legacy) is not legacy


def test_local_checks_cover_the_schema_structure() -> None:
    with pytest.raises(ValidationError):
        TaskCall(name="not a task name")
    with pytest.raises(ValidationError):
        CustomOneQubit(step_name="coherence", tasks=[])
    with pytest.raises(ValidationError):
        Pipeline(targets=Qubits(["0"]), steps=[])
    with pytest.raises(ValidationError):
        CustomOneQubit(step_name="Coherence", tasks=[TaskCall(name="CheckT1")])
    with pytest.raises(ValidationError):
        Pipeline(targets=Qubits(["0"]), steps=[{"type": "NoSuchStep"}])


def test_server_only_rules_are_not_checked_locally() -> None:
    # A repeated task without call_ids is rejected by the server, not by the SDK.
    pipeline = Pipeline(
        targets=Qubits(["0"]),
        steps=[CustomOneQubit(tasks=[TaskCall(name="CheckT1"), TaskCall(name="CheckT1")])],
    )

    assert [call["name"] for call in pipeline.to_spec()["steps"][0]["tasks"]] == [
        "CheckT1",
        "CheckT1",
    ]


def test_qubits_needs_a_list_of_ids() -> None:
    with pytest.raises(TypeError):
        Qubits("01")


def test_to_spec_rejects_other_types() -> None:
    with pytest.raises(TypeError):
        to_spec(["not", "a", "spec"])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("declaration", "expected"),
    [
        (sweep.linspace(0, 1, 3), {"value": [0, 1, 3], "value_type": "np.linspace"}),
        (sweep.logspace(1, 2, 5), {"value": [1, 2, 5], "value_type": "np.logspace"}),
        (sweep.arange(0, 10, 2.5), {"value": [0, 10, 2.5], "value_type": "np.arange"}),
        (sweep.range(0, 10, 2), {"value": [0, 10, 2], "value_type": "range"}),
        (sweep.values(1, 2.5), {"value": [1, 2.5], "value_type": "list"}),
    ],
)
def test_sweeps_write_the_wire_format(
    declaration: dict[str, Any], expected: dict[str, Any]
) -> None:
    assert declaration == expected


def test_sweeps_reject_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="num"):
        sweep.linspace(0, 1, 0)
    with pytest.raises(ValueError, match="step"):
        sweep.arange(0, 1, 0)
    with pytest.raises(TypeError):
        sweep.range(0, 1.5, 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        sweep.logspace(True, 2, 3)
    with pytest.raises(ValueError, match="at least one"):
        sweep.values()


def test_string_literals_match_the_generated_enums() -> None:
    from typing import get_args

    from qdash.client.services import models
    from qdash.sdk.pipeline import OneQubitExecutionMode, OnFailure

    assert set(get_args(OneQubitExecutionMode)) == {mode.value for mode in models.ExecutionMode}
    assert set(get_args(OnFailure)) == {value.value for value in models.OnFailure}
