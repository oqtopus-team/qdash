"""Tests for TaskResultProcessor."""

import pytest
from qdash.datamodel.task import OutputParameterModel
from qdash.workflow.engine.calibration.task_result_processor import (
    FidelityValidationError,
    R2ValidationError,
    TaskResultProcessor,
)


class TestR2Validation:
    """Test R² validation."""

    def test_validate_r2_passes_when_above_threshold(self):
        """Test validate_r2 passes when R² is above threshold."""
        processor = TaskResultProcessor(r2_threshold=0.7)

        result = processor.validate_r2({"0": 0.95}, "0")

        assert result is True

    def test_validate_r2_raises_when_below_threshold(self):
        """Test validate_r2 raises when R² is below threshold."""
        processor = TaskResultProcessor(r2_threshold=0.7)

        with pytest.raises(R2ValidationError, match="R² value too low"):
            processor.validate_r2({"0": 0.3}, "0")

    def test_validate_r2_raises_when_equal_to_threshold(self):
        """Test validate_r2 raises when R² equals threshold."""
        processor = TaskResultProcessor(r2_threshold=0.7)

        with pytest.raises(R2ValidationError):
            processor.validate_r2({"0": 0.7}, "0")

    def test_validate_r2_passes_when_r2_is_none(self):
        """Test validate_r2 passes when R² is None."""
        processor = TaskResultProcessor()

        result = processor.validate_r2(None, "0")

        assert result is True

    def test_validate_r2_passes_when_qid_not_in_r2(self):
        """Test validate_r2 passes when qid not in R² dict."""
        processor = TaskResultProcessor()

        result = processor.validate_r2({"1": 0.5}, "0")

        assert result is True

    def test_validate_r2_uses_custom_threshold(self):
        """Test validate_r2 uses custom threshold when provided."""
        processor = TaskResultProcessor(r2_threshold=0.7)

        # Should pass with custom threshold of 0.3
        result = processor.validate_r2({"0": 0.5}, "0", threshold=0.3)
        assert result is True

        # Should fail with custom threshold of 0.8
        with pytest.raises(R2ValidationError):
            processor.validate_r2({"0": 0.5}, "0", threshold=0.8)


class TestFidelityValidation:
    """Test fidelity validation."""

    def test_validate_fidelity_passes_for_normal_values(self):
        """Test validate_fidelity passes for fidelity <= 1.0."""
        processor = TaskResultProcessor()
        output_params = {"fidelity": OutputParameterModel(value=0.99)}

        result = processor.validate_fidelity(output_params, "RandomizedBenchmarking")

        assert result is True

    def test_validate_fidelity_raises_for_over_100_percent(self):
        """Test validate_fidelity raises for fidelity > 1.0."""
        processor = TaskResultProcessor()
        output_params = {"fidelity": OutputParameterModel(value=1.5)}

        with pytest.raises(FidelityValidationError, match="exceeds 100%"):
            processor.validate_fidelity(output_params, "RandomizedBenchmarking")

    def test_validate_fidelity_skips_non_rb_tasks(self):
        """Test validate_fidelity skips validation for non-RB tasks."""
        processor = TaskResultProcessor()
        output_params = {"fidelity": OutputParameterModel(value=1.5)}

        # Should pass even with invalid fidelity for non-RB task
        result = processor.validate_fidelity(output_params, "CheckRabi")

        assert result is True

    def test_validate_fidelity_passes_when_no_fidelity(self):
        """Test validate_fidelity passes when fidelity param missing."""
        processor = TaskResultProcessor()
        output_params = {"other_param": OutputParameterModel(value=5.0)}

        result = processor.validate_fidelity(output_params, "RandomizedBenchmarking")

        assert result is True

    def test_validate_fidelity_handles_interleaved_rb(self):
        """Test validate_fidelity handles InterleavedRandomizedBenchmarking."""
        processor = TaskResultProcessor()
        output_params = {"fidelity": OutputParameterModel(value=1.5)}

        with pytest.raises(FidelityValidationError):
            processor.validate_fidelity(output_params, "InterleavedRandomizedBenchmarking")


class TestOutputParameterProcessing:
    """Test output parameter processing."""

    def test_get_output_parameter_names(self):
        """Test get_output_parameter_names returns param names."""
        processor = TaskResultProcessor()
        output_params = {
            "qubit_frequency": OutputParameterModel(value=5.0),
            "t1": OutputParameterModel(value=100.0),
        }

        names = processor.get_output_parameter_names(output_params)

        assert set(names) == {"qubit_frequency", "t1"}

    def test_filter_output_parameters_on_r2_failure(self):
        """Test filter_output_parameters_on_r2_failure returns empty dict."""
        processor = TaskResultProcessor()
        output_params = {
            "qubit_frequency": OutputParameterModel(value=5.0),
            "t1": OutputParameterModel(value=100.0),
        }

        result = processor.filter_output_parameters_on_r2_failure(output_params)

        assert result == {}

    def test_process_output_parameters_attaches_ids(self):
        """Test process_output_parameters attaches execution and task IDs."""
        processor = TaskResultProcessor()
        output_params = {
            "qubit_frequency": OutputParameterModel(value=5.0),
        }

        result = processor.process_output_parameters(
            output_params, "CheckRabi", "exec-001", "task-001"
        )

        assert result["qubit_frequency"].execution_id == "exec-001"
        assert result["qubit_frequency"].task_id == "task-001"

    def test_process_output_parameters_validates_fidelity(self):
        """Test process_output_parameters validates fidelity for RB tasks."""
        processor = TaskResultProcessor()
        output_params = {"fidelity": OutputParameterModel(value=1.5)}

        with pytest.raises(FidelityValidationError):
            processor.process_output_parameters(
                output_params, "RandomizedBenchmarking", "exec-001", "task-001"
            )


class TestRunResultProcessing:
    """Test run result processing."""

    def test_process_run_result_returns_result_info(self):
        """Test process_run_result returns processed info."""
        processor = TaskResultProcessor()
        raw_result = {"data": [1, 2, 3]}
        r2 = {"0": 0.95}

        result = processor.process_run_result(raw_result, r2, "0", "CheckRabi")

        assert result["raw_result"] == raw_result
        assert result["r2"] == r2
        assert result["r2_valid"] is True

    def test_process_run_result_raises_on_low_r2(self):
        """Test process_run_result raises on low R²."""
        processor = TaskResultProcessor(r2_threshold=0.7)
        raw_result = {"data": [1, 2, 3]}
        r2 = {"0": 0.3}

        with pytest.raises(R2ValidationError):
            processor.process_run_result(raw_result, r2, "0", "CheckRabi")

    def test_process_run_result_passes_with_none_r2(self):
        """Test process_run_result passes with None R²."""
        processor = TaskResultProcessor()
        raw_result = {"data": [1, 2, 3]}

        result = processor.process_run_result(raw_result, None, "0", "CheckRabi")

        assert result["r2_valid"] is True
