"""Tests for task datamodel, focusing on BaseTaskResultModel."""

from qdash.datamodel.task import QubitTaskModel, RunParameterModel


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
