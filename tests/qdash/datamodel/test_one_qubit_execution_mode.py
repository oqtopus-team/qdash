"""One-qubit execution mode names, their deprecated aliases, and pipeline spec parsing."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from qdash.datamodel.calibration_pipeline import (
    ONE_QUBIT_MODES,
    CalibrationPipelineSpec,
    pipeline_warnings,
)
from qdash.datamodel.one_qubit_execution_mode import (
    LEGACY_ONE_QUBIT_EXECUTION_MODES,
    ONE_QUBIT_EXECUTION_MODES,
    normalize_one_qubit_execution_mode,
    resolve_one_qubit_execution_mode,
)

LEGACY = [
    ("synchronized", "parallel_by_round"),
    ("scheduled", "parallel_by_mux"),
    ("serial", "sequential"),
]


def test_canonical_names_and_aliases() -> None:
    assert set(ONE_QUBIT_EXECUTION_MODES) == {
        "parallel_by_round",
        "parallel_by_mux",
        "sequential",
        "simultaneous_spectroscopy",
    }
    assert dict(LEGACY) == LEGACY_ONE_QUBIT_EXECUTION_MODES
    # The pipeline catalog lists only the canonical names.
    assert ONE_QUBIT_MODES == ONE_QUBIT_EXECUTION_MODES


@pytest.mark.parametrize("canonical", ONE_QUBIT_EXECUTION_MODES)
def test_canonical_values_resolve_without_notes(canonical: str) -> None:
    assert normalize_one_qubit_execution_mode(canonical, default="sequential") == (canonical, [])


def test_default_applies_only_when_nothing_is_given() -> None:
    assert normalize_one_qubit_execution_mode(None, None, default="parallel_by_mux") == (
        "parallel_by_mux",
        [],
    )


@pytest.mark.parametrize(("legacy", "canonical"), LEGACY)
def test_legacy_value_in_execution_mode_is_mapped_with_a_note(legacy: str, canonical: str) -> None:
    resolved, notes = normalize_one_qubit_execution_mode(legacy, default="sequential")
    assert resolved == canonical
    assert len(notes) == 1
    assert "deprecated" in notes[0] and repr(canonical) in notes[0]


@pytest.mark.parametrize(("legacy", "canonical"), LEGACY)
def test_legacy_mode_keyword_is_mapped_with_one_note(legacy: str, canonical: str) -> None:
    resolved, notes = normalize_one_qubit_execution_mode(None, legacy, default="sequential")
    assert resolved == canonical
    assert notes == [
        f"mode={legacy!r} is deprecated and still accepted; "
        f"set execution_mode={canonical!r} instead"
    ]


@pytest.mark.parametrize(("legacy", "canonical"), LEGACY)
def test_equivalent_explicit_values_are_accepted(legacy: str, canonical: str) -> None:
    resolved, notes = normalize_one_qubit_execution_mode(canonical, legacy, default="sequential")
    assert resolved == canonical
    assert len(notes) == 1  # only the deprecated keyword


def test_conflicting_explicit_values_raise() -> None:
    with pytest.raises(ValueError, match=r"conflicts with the deprecated Step\.mode=.serial."):
        normalize_one_qubit_execution_mode(
            "parallel_by_mux", "serial", default="parallel_by_mux", where="Step."
        )


def test_unknown_values_raise() -> None:
    with pytest.raises(ValueError, match="Unknown execution_mode 'fast'"):
        normalize_one_qubit_execution_mode("fast", default="sequential")
    with pytest.raises(ValueError, match="Unknown mode 'fast'"):
        normalize_one_qubit_execution_mode(None, "fast", default="sequential")


def test_resolve_emits_deprecation_warnings() -> None:
    with pytest.warns(DeprecationWarning, match="set execution_mode='parallel_by_round'"):
        assert resolve_one_qubit_execution_mode(None, "synchronized", default="sequential") == (
            "parallel_by_round",
            [
                "mode='synchronized' is deprecated and still accepted; "
                "set execution_mode='parallel_by_round' instead"
            ],
        )


# ---------------------------------------------------------------------------
# Pipeline spec
# ---------------------------------------------------------------------------


def _spec(*steps: dict[str, Any]) -> dict[str, Any]:
    return {"spec_version": 2, "targets": {"qids": ["0", "1"]}, "steps": list(steps)}


def _custom(**fields: Any) -> dict[str, Any]:
    return {"type": "CustomOneQubit", "tasks": [{"name": "CheckRabi"}], **fields}


@pytest.mark.parametrize("step_type", ["OneQubitCheck", "OneQubitFineTune", "CustomOneQubit"])
def test_spec_default_execution_mode_is_parallel_by_round(step_type: str) -> None:
    step: dict[str, Any] = _custom() if step_type == "CustomOneQubit" else {"type": step_type}
    parsed = CalibrationPipelineSpec.model_validate(_spec(step))
    assert parsed.steps[0].execution_mode == "parallel_by_round"  # type: ignore[union-attr]
    assert pipeline_warnings(parsed) == []


@pytest.mark.parametrize(("legacy", "canonical"), [*LEGACY, ("simultaneous_spectroscopy",) * 2])
def test_legacy_spec_mode_parses_to_the_same_spec(legacy: str, canonical: str) -> None:
    old = CalibrationPipelineSpec.model_validate(_spec(_custom(mode=legacy)))
    new = CalibrationPipelineSpec.model_validate(_spec(_custom(execution_mode=canonical)))

    assert old.steps[0].execution_mode == canonical  # type: ignore[union-attr]
    assert old.model_dump(mode="json") == new.model_dump(mode="json")
    assert old.plan_digest() == new.plan_digest()
    assert "mode" not in old.model_dump(mode="json")["steps"][0]
    [(path, message)] = pipeline_warnings(old)
    assert path == "steps[0]"
    assert f"set execution_mode={canonical!r}" in message
    assert pipeline_warnings(new) == []


def test_legacy_value_in_spec_execution_mode_is_accepted_with_a_warning() -> None:
    parsed = CalibrationPipelineSpec.model_validate(
        _spec({"type": "OneQubitCheck", "execution_mode": "scheduled"})
    )
    assert parsed.steps[0].execution_mode == "parallel_by_mux"  # type: ignore[union-attr]
    [(path, message)] = pipeline_warnings(parsed)
    assert path == "steps[0]" and "'parallel_by_mux'" in message


def test_equivalent_spec_mode_and_execution_mode_are_accepted() -> None:
    parsed = CalibrationPipelineSpec.model_validate(
        _spec(_custom(mode="scheduled", execution_mode="parallel_by_mux"))
    )
    assert parsed.steps[0].execution_mode == "parallel_by_mux"  # type: ignore[union-attr]
    assert len(pipeline_warnings(parsed)) == 1


def test_conflicting_spec_mode_and_execution_mode_are_rejected() -> None:
    with pytest.raises(ValidationError, match="conflicts with the deprecated mode='serial'"):
        CalibrationPipelineSpec.model_validate(
            _spec(_custom(mode="serial", execution_mode="parallel_by_mux"))
        )


def test_spec_rejects_unknown_modes() -> None:
    with pytest.raises(ValidationError, match="Unknown mode 'fast'"):
        CalibrationPipelineSpec.model_validate(_spec(_custom(mode="fast")))
    with pytest.raises(ValidationError):
        CalibrationPipelineSpec.model_validate(_spec(_custom(execution_mode="fast")))


def test_normalized_spec_round_trips_without_warnings() -> None:
    parsed = CalibrationPipelineSpec.model_validate(_spec(_custom(mode="serial")))
    again = CalibrationPipelineSpec.model_validate(parsed.model_dump(mode="json"))
    assert again.model_dump(mode="json") == parsed.model_dump(mode="json")
    assert pipeline_warnings(again) == []


def test_schema_documents_execution_mode() -> None:
    schema = CalibrationPipelineSpec.model_json_schema()
    check = schema["$defs"]["OneQubitCheckStep"]["properties"]
    assert "mode" not in check
    assert check["execution_mode"]["default"] == "parallel_by_round"
    assert set(check["execution_mode"]["enum"]) == set(ONE_QUBIT_EXECUTION_MODES)
    assert "deprecated `mode`" in check["execution_mode"]["description"]
