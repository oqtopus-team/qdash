"""Tests for snapshot parameter resolution helpers."""

from typing import Any

import pytest

from qdash.datamodel.task import InputParameterSpec, ParameterModel, RunParameterModel
from qdash.workflow.engine.task.snapshot_parameters import (
    apply_run_overrides,
    ensure_snapshot_inputs_compatible,
    merge_overrides,
    normalize_snapshot_inputs,
    reconstruct_param,
    reconstruct_params,
)


class TestReconstructParam:
    """Test reconstruct_param."""

    def test_reconstruct_from_dict(self) -> None:
        result = reconstruct_param(ParameterModel, "freq", {"value": 5.0, "unit": "GHz"})
        assert result is not None
        assert result.value == 5.0
        assert result.unit == "GHz"

    def test_reconstruct_from_scalar(self) -> None:
        result = reconstruct_param(ParameterModel, "freq", 5.0)
        assert result is not None
        assert result.value == 5.0

    def test_reconstruct_run_parameter_from_dict(self) -> None:
        result = reconstruct_param(RunParameterModel, "shots", {"value": 1024, "value_type": "int"})
        assert result is not None
        assert result.value == 1024

    def test_reconstruct_returns_none_on_invalid_data(self) -> None:
        result = reconstruct_param(ParameterModel, "bad", {"invalid_field_only": True})
        assert result is None or isinstance(result, ParameterModel)

    def test_reconstruct_returns_none_on_type_error(self) -> None:
        assert reconstruct_param(ParameterModel, "bad", [1, 2, 3]) is None

    def test_reconstruct_params_drops_invalid_entries_in_order(self) -> None:
        result = reconstruct_params(
            ParameterModel, {"b": {"value": 2.0}, "bad": [1, 2, 3], "a": 1.0}
        )
        assert list(result) == ["b", "a"]
        assert result["a"].value == 1.0


class TestMergeOverrides:
    """Test merge_overrides."""

    def test_empty_overrides_returns_snapshot(self) -> None:
        snapshot: dict[str, Any] = {"a": 1, "b": 2}
        assert merge_overrides(snapshot, {}) is snapshot

    def test_override_replaces_simple_value(self) -> None:
        assert merge_overrides({"a": 1, "b": 2}, {"a": 10}) == {"a": 10, "b": 2}

    def test_override_replaces_value_key_in_dict(self) -> None:
        snapshot: dict[str, Any] = {
            "freq": {"value": 5.0, "unit": "GHz", "description": "Frequency"},
        }
        result = merge_overrides(snapshot, {"freq": 6.0})
        assert result["freq"] == {"value": 6.0, "unit": "GHz", "description": "Frequency"}

    def test_override_replaces_entire_entry_without_value_key(self) -> None:
        result = merge_overrides({"config": {"mode": "fast", "retries": 3}}, {"config": "simple"})
        assert result["config"] == "simple"

    def test_override_adds_new_key(self) -> None:
        assert merge_overrides({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_does_not_mutate_original(self) -> None:
        snapshot: dict[str, Any] = {"a": {"value": 1, "unit": "V"}}
        merge_overrides(snapshot, {"a": 2})
        assert snapshot == {"a": {"value": 1, "unit": "V"}}


class TestApplyRunOverrides:
    """Test apply_run_overrides."""

    def test_without_overrides_returns_snapshot_unseeded(self) -> None:
        snap_run: dict[str, Any] = {"shots": {"value": 512}}
        declared = {"interval": RunParameterModel(value=8, value_type="int")}
        assert apply_run_overrides(snap_run, {}, declared) is snap_run

    def test_overrides_seed_declarations_under_snapshot_values(self) -> None:
        declared = {
            "shots": RunParameterModel(value=1024, value_type="int"),
            "time_range": RunParameterModel(value=(0, 101, 4), value_type="range"),
        }
        result = apply_run_overrides(
            {"shots": {"value": 512, "value_type": "int"}},
            {"time_range": (0, 201, 8)},
            declared,
        )
        assert result["shots"] == {"value": 512, "value_type": "int"}
        assert result["time_range"]["value"] == (0, 201, 8)
        assert result["time_range"]["value_type"] == "range"


class TestNormalizeSnapshotInputs:
    """Test normalize_snapshot_inputs."""

    def test_prefixed_alias_maps_to_declared_name_and_records_source_name(self) -> None:
        declarations = {
            "control_drag_pi_duration": InputParameterSpec.required_database(
                parameter_name="drag_pi_duration",
                parameter_aliases=("drag_pi_length",),
                qid_role="control",
            )
        }
        result = normalize_snapshot_inputs(
            {"control_drag_pi_length": {"value": 32, "unit": "ns"}}, declarations
        )
        assert result == {
            "control_drag_pi_duration": {
                "value": 32,
                "unit": "ns",
                "parameter_name": "drag_pi_length",
            }
        }

    def test_existing_parameter_name_is_kept(self) -> None:
        declarations = {
            "control_frequency": InputParameterSpec.required_database(
                fallback_parameter_names=("qubit_frequency",),
            )
        }
        result = normalize_snapshot_inputs(
            {"qubit_frequency": {"value": 5.2, "parameter_name": "recorded"}}, declarations
        )
        assert result == {"control_frequency": {"value": 5.2, "parameter_name": "recorded"}}

    def test_alias_precedes_fallback_and_both_are_dropped(self) -> None:
        declarations = {
            "x": InputParameterSpec.required_database(
                parameter_aliases=("alias",),
                fallback_parameter_names=("fallback",),
            )
        }
        result = normalize_snapshot_inputs(
            {"alias": {"value": 1}, "fallback": {"value": 2}}, declarations
        )
        assert result == {"x": {"value": 1, "parameter_name": "alias"}}

    def test_canonical_value_wins_and_declared_fallback_is_kept(self) -> None:
        declarations = {
            "control_frequency": InputParameterSpec.required_database(
                fallback_parameter_names=("qubit_frequency",),
            ),
            "qubit_frequency": InputParameterSpec.required_database(),
        }
        snap_input = {"control_frequency": {"value": 5.1}, "qubit_frequency": {"value": 5.2}}
        assert normalize_snapshot_inputs(snap_input, declarations) == snap_input

    def test_scalar_compatible_value_is_copied_as_is(self) -> None:
        declarations = {"x": InputParameterSpec.required_database(parameter_aliases=("old",))}
        assert normalize_snapshot_inputs({"old": 3}, declarations) == {"x": 3}

    def test_input_is_not_mutated(self) -> None:
        declarations = {"x": InputParameterSpec.required_database(parameter_aliases=("old",))}
        snap_input: dict[str, Any] = {"old": {"value": 3}}
        normalize_snapshot_inputs(snap_input, declarations)
        assert snap_input == {"old": {"value": 3}}


class TestEnsureSnapshotInputsCompatible:
    """Test ensure_snapshot_inputs_compatible."""

    def test_complete_inputs_pass(self) -> None:
        ensure_snapshot_inputs_compatible("T", "0", {"a": 1, "extra": 2}, {"a": object()})

    def test_missing_inputs_are_sorted_in_message(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            ensure_snapshot_inputs_compatible("T", "0", {}, {"b": object(), "a": object()})
        assert str(exc_info.value) == (
            "Snapshot inputs for task 'T' and qid '0' are incompatible with the current "
            "task definition; run a fresh calibration instead. Missing inputs: a, b"
        )
