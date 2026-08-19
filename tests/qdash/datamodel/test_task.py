"""Tests for task datamodel, focusing on BaseTaskResultModel."""

import pytest
from pydantic import ValidationError

from qdash.datamodel.task import (
    InputParameterModel,
    InputParameterSpec,
    OutputParameterModel,
    OutputParameterSpec,
    QubitTaskModel,
    RunParameterModel,
    RunParameterSpec,
)


def test_calibration_input_resolution_rejects_contradictory_default() -> None:
    with pytest.raises(ValidationError, match="database_required must not declare"):
        InputParameterSpec(
            resolution="database_required",
            user_override="allowed",
            default=1.0,
        )


def test_calibration_input_validates_effective_numeric_bounds_without_fallback() -> None:
    declaration = InputParameterSpec(
        resolution="database_or_default",
        user_override="allowed",
        default=0.1,
        greater_than=0.0,
        less_than=1.0,
    )

    declaration.validate_effective_value("amplitude", 0.5)

    with pytest.raises(ValueError, match="must be greater than"):
        declaration.validate_effective_value("amplitude", 0.0)
    with pytest.raises(ValueError, match="must be less than"):
        declaration.validate_effective_value("amplitude", 1.0)
    with pytest.raises(ValueError, match="must be finite"):
        declaration.validate_effective_value("amplitude", float("nan"))


def test_calibration_input_rejects_inverted_numeric_bounds() -> None:
    with pytest.raises(ValidationError, match="greater_than must be less than"):
        InputParameterSpec(
            resolution="database_or_default",
            user_override="allowed",
            default=0.1,
            greater_than=1.0,
            less_than=0.0,
        )

    with pytest.raises(ValidationError, match="database_or_default requires"):
        InputParameterSpec(
            resolution="database_or_default",
            user_override="allowed",
            default=None,
        )


def test_parameter_specs_create_matching_runtime_models() -> None:
    input_model = InputParameterSpec.default_only(default=1.0, unit="GHz").create_model()
    run_model = RunParameterSpec(default=1024, value_type="int").create_model()
    output_model = OutputParameterSpec(default=0.5, unit="a.u.").create_model()

    assert isinstance(input_model, InputParameterModel)
    assert input_model.value == 1.0
    assert isinstance(run_model, RunParameterModel)
    assert run_model.value == 1024
    assert isinstance(output_model, OutputParameterModel)
    assert output_model.value == 0.5


class TestBaseTaskResultModelRunParameters:
    """Test run_parameters field and put_run_parameter method."""

    def test_run_parameters_default_empty(self):
        """Test run_parameters defaults to empty dict."""
        model = QubitTaskModel(qid="0", name="CheckRabi")
        assert model.run_parameters == {}

    def test_put_run_parameter_stores_dict(self):
        """Test put_run_parameter stores run parameters."""
        model = QubitTaskModel(qid="0", name="CheckRabi")
        run_params = {
            "shots": {"value": 1024, "value_type": "int", "unit": "", "description": ""},
            "interval": {"value": 150, "value_type": "int", "unit": "us", "description": ""},
        }

        model.put_run_parameter(run_params)

        assert model.run_parameters == run_params
        assert model.run_parameters["shots"]["value"] == 1024

    def test_put_run_parameter_deep_copies(self):
        """Test put_run_parameter deep copies the input to avoid mutation."""
        model = QubitTaskModel(qid="0", name="CheckRabi")
        run_params = {"shots": {"value": 1024}}

        model.put_run_parameter(run_params)

        # Mutate the original - should not affect the stored copy
        run_params["shots"]["value"] = 9999
        assert model.run_parameters["shots"]["value"] == 1024

    def test_put_run_parameter_overwrites_previous(self):
        """Test put_run_parameter overwrites previous run_parameters."""
        model = QubitTaskModel(qid="0", name="CheckRabi")
        model.put_run_parameter({"shots": {"value": 512}})
        model.put_run_parameter({"interval": {"value": 200}})

        assert "shots" not in model.run_parameters
        assert model.run_parameters["interval"]["value"] == 200

    def test_run_parameters_serialization(self):
        """Test run_parameters is included in model_dump."""
        model = QubitTaskModel(qid="0", name="CheckRabi")
        model.put_run_parameter({"shots": {"value": 1024}})

        dumped = model.model_dump()
        assert "run_parameters" in dumped
        assert dumped["run_parameters"]["shots"]["value"] == 1024


class TestRunParameterModelDump:
    """Test RunParameterModel serialization for storage."""

    def test_model_dump_produces_storable_dict(self):
        """Test model_dump produces a dict suitable for MongoDB storage."""
        param = RunParameterModel(
            value=1024, value_type="int", unit="", description="Number of shots"
        )
        dumped = param.model_dump()

        assert dumped == {
            "value": 1024,
            "value_type": "int",
            "unit": "",
            "description": "Number of shots",
        }

    def test_model_dump_with_tuple_value(self):
        """Test model_dump handles tuple values (e.g., np.linspace args)."""
        param = RunParameterModel(
            value=(0, 100, 50), value_type="np.linspace", unit="ns", description="Time range"
        )
        dumped = param.model_dump()

        assert dumped["value"] == (0, 100, 50)
        assert dumped["value_type"] == "np.linspace"
        assert dumped["unit"] == "ns"
