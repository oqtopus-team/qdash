"""One-qubit execution mode values and their validation in pipeline specs."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from qdash.datamodel.calibration_pipeline import CalibrationPipelineSpec, pipeline_warnings
from qdash.datamodel.one_qubit_execution_mode import (
    ONE_QUBIT_EXECUTION_MODES,
    validate_one_qubit_execution_mode,
)

# Names used before the rename; they are no longer accepted anywhere.
REMOVED = ["synchronized", "scheduled", "serial"]


def test_execution_modes_are_the_canonical_names() -> None:
    assert set(ONE_QUBIT_EXECUTION_MODES) == {
        "parallel_by_round",
        "parallel_by_mux",
        "sequential",
        "simultaneous_spectroscopy",
    }


@pytest.mark.parametrize("mode", ONE_QUBIT_EXECUTION_MODES)
def test_validate_accepts_every_canonical_mode(mode: str) -> None:
    assert validate_one_qubit_execution_mode(mode) == mode


@pytest.mark.parametrize("value", [*REMOVED, "fast", None, 1])
def test_validate_rejects_removed_and_unknown_values(value: object) -> None:
    with pytest.raises(ValueError, match=r"Unknown execution_mode .*Valid execution modes"):
        validate_one_qubit_execution_mode(value)


# ---------------------------------------------------------------------------
# Pipeline spec
# ---------------------------------------------------------------------------


def _spec(*steps: dict[str, Any]) -> dict[str, Any]:
    return {"spec_version": 2, "targets": {"qids": ["0", "1"]}, "steps": list(steps)}


def _custom(**fields: Any) -> dict[str, Any]:
    return {"type": "CustomOneQubit", "tasks": [{"name": "CheckRabi"}], **fields}


def _step(step_type: str, **fields: Any) -> dict[str, Any]:
    return _custom(**fields) if step_type == "CustomOneQubit" else {"type": step_type, **fields}


STEP_TYPES = ["OneQubitCheck", "OneQubitFineTune", "CustomOneQubit"]


@pytest.mark.parametrize("step_type", STEP_TYPES)
def test_spec_default_execution_mode_is_parallel_by_round(step_type: str) -> None:
    parsed = CalibrationPipelineSpec.model_validate(_spec(_step(step_type)))
    assert parsed.steps[0].execution_mode == "parallel_by_round"  # type: ignore[union-attr]
    assert pipeline_warnings(parsed) == []


@pytest.mark.parametrize("mode", ONE_QUBIT_EXECUTION_MODES)
def test_spec_accepts_canonical_modes_and_round_trips(mode: str) -> None:
    parsed = CalibrationPipelineSpec.model_validate(_spec(_custom(execution_mode=mode)))
    assert parsed.steps[0].execution_mode == mode  # type: ignore[union-attr]
    again = CalibrationPipelineSpec.model_validate(parsed.model_dump(mode="json"))
    assert again.model_dump(mode="json") == parsed.model_dump(mode="json")
    assert pipeline_warnings(parsed) == []


@pytest.mark.parametrize("step_type", STEP_TYPES)
@pytest.mark.parametrize("old", REMOVED)
def test_spec_rejects_removed_mode_names(step_type: str, old: str) -> None:
    with pytest.raises(ValidationError, match="execution_mode"):
        CalibrationPipelineSpec.model_validate(_spec(_step(step_type, execution_mode=old)))


@pytest.mark.parametrize("step_type", STEP_TYPES)
@pytest.mark.parametrize("value", [*REMOVED, "parallel_by_mux"])
def test_spec_rejects_the_removed_mode_key(step_type: str, value: str) -> None:
    # A saved spec that still uses ``mode`` fails instead of silently running the default.
    with pytest.raises(ValidationError, match="mode\n  Extra inputs are not permitted"):
        CalibrationPipelineSpec.model_validate(_spec(_step(step_type, mode=value)))


def test_schema_documents_execution_mode_only() -> None:
    schema = CalibrationPipelineSpec.model_json_schema()
    for name in ("OneQubitCheckStep", "OneQubitFineTuneStep", "CustomOneQubitStep"):
        properties = schema["$defs"][name]["properties"]
        assert "mode" not in properties
        assert properties["execution_mode"]["default"] == "parallel_by_round"
        assert set(properties["execution_mode"]["enum"]) == set(ONE_QUBIT_EXECUTION_MODES)
        description = properties["execution_mode"]["description"]
        assert "rounds" in description and "deprecated" not in description
