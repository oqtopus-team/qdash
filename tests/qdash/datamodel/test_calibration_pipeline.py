"""Tests for the declarative calibration pipeline spec."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from qdash.datamodel.calibration_pipeline import (
    CHECK_1Q_TASKS,
    FULL_2Q_TASKS,
    STEP_CATALOG,
    CalibrationPipelineSpec,
    pipeline_spec_json_schema,
    step_tasks,
)


def spec(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "targets": {"qids": ["0", "1"]},
        "steps": [{"type": "OneQubitCheck"}],
    }
    base.update(overrides)
    return base


def test_defaults_fill_in_the_template_task_lists() -> None:
    parsed = CalibrationPipelineSpec.model_validate(
        spec(steps=[{"type": "OneQubitCheck"}, {"type": "TwoQubitCalibration"}])
    )
    assert step_tasks(parsed.steps[0]) == CHECK_1Q_TASKS
    assert step_tasks(parsed.steps[1]) == FULL_2Q_TASKS
    assert parsed.name == "pipeline"
    assert parsed.all_tasks() == CHECK_1Q_TASKS + FULL_2Q_TASKS


def test_targets_need_exactly_one_kind() -> None:
    with pytest.raises(ValidationError, match="exactly one of qids or mux_ids"):
        CalibrationPipelineSpec.model_validate(spec(targets={}))
    with pytest.raises(ValidationError, match="exactly one of qids or mux_ids"):
        CalibrationPipelineSpec.model_validate(spec(targets={"qids": ["0"], "mux_ids": [0]}))
    with pytest.raises(ValidationError, match="exclude_qids only applies"):
        CalibrationPipelineSpec.model_validate(spec(targets={"qids": ["0"], "exclude_qids": ["1"]}))
    parsed = CalibrationPipelineSpec.model_validate(
        spec(targets={"mux_ids": [0, 1], "exclude_qids": ["5"]})
    )
    assert parsed.targets.mux_ids == [0, 1]


def test_filters_need_a_one_qubit_step_before_them() -> None:
    with pytest.raises(ValidationError, match="needs one_qubit_check or one_qubit_fine_tune"):
        CalibrationPipelineSpec.model_validate(spec(steps=[{"type": "FilterByStatus"}]))
    # Either one-qubit step satisfies the filter, as in Pipeline._validate.
    CalibrationPipelineSpec.model_validate(
        spec(steps=[{"type": "OneQubitFineTune"}, {"type": "FilterByStatus"}])
    )
    CalibrationPipelineSpec.model_validate(
        spec(
            steps=[
                {"type": "OneQubitCheck"},
                {"type": "FilterByMetric", "metric": "t1", "threshold": 30},
                {"type": "GenerateCRSchedule"},
                {"type": "TwoQubitCalibration"},
            ]
        )
    )


def test_unknown_step_types_and_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="does not match any of the expected tags"):
        CalibrationPipelineSpec.model_validate(spec(steps=[{"type": "RunShell"}]))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CalibrationPipelineSpec.model_validate(
            spec(steps=[{"type": "OneQubitCheck", "command": "rm -rf /"}])
        )
    with pytest.raises(ValidationError):
        CalibrationPipelineSpec.model_validate(
            spec(steps=[{"type": "OneQubitCheck", "mode": "parallel"}])
        )


def test_custom_steps_need_tasks_and_unique_names() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        CalibrationPipelineSpec.model_validate(
            spec(steps=[{"type": "CustomOneQubit", "tasks": []}])
        )
    with pytest.raises(ValidationError, match="reuses step_name"):
        CalibrationPipelineSpec.model_validate(
            spec(
                steps=[
                    {"type": "CustomOneQubit", "step_name": "a", "tasks": ["CheckT1"]},
                    {"type": "CustomOneQubit", "step_name": "a", "tasks": ["CheckT2Echo"]},
                ]
            )
        )
    parsed = CalibrationPipelineSpec.model_validate(
        spec(
            steps=[
                {"type": "CustomOneQubit", "step_name": "coh", "tasks": ["CheckT1"]},
                {"type": "CustomOneQubit", "tasks": ["CheckRamsey"]},
            ]
        )
    )
    assert [step.step_name for step in parsed.steps] == ["coh", "custom_one_qubit"]  # type: ignore[union-attr]


def test_json_schema_lists_every_step_type() -> None:
    schema = pipeline_spec_json_schema()
    defs = schema["$defs"]
    for step_type in STEP_CATALOG:
        assert f"{step_type}Step" in defs, step_type
    assert schema["required"] == ["targets", "steps"]
