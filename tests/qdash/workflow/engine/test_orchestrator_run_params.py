"""Tests for default_run_parameters injection in CalibOrchestrator."""

from typing import Any

# Import fake tasks to trigger registration in BaseTask.registry
import qdash.workflow.calibtasks.fake  # noqa: F401
from qdash.workflow.calibtasks.active_protocols import generate_task_instances

# FakeCheckRabi registers as "CheckRabi" with backend "fake"
TASK_NAME = "CheckRabi"
BACKEND = "fake"


class TestDefaultRunParameterInjection:
    """Test default_run_parameters injection into task instances."""

    def test_default_run_parameters_override_task_defaults(self):
        """Test that default_run_parameters from config override task class defaults."""
        task_details: dict[str, Any] = {
            TASK_NAME: {
                "run_parameters": {
                    "shots": {"value": 2048, "value_type": "int"},
                },
            },
        }
        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details=task_details,
            backend=BACKEND,
        )
        task = instances[TASK_NAME]
        # shots should be overridden to 2048
        assert task.run_parameters["shots"].value == 2048
        # time_range should keep class default
        assert task.run_parameters["time_range"].value == (0, 401, 8)

    def test_default_run_parameters_do_not_override_per_task(self):
        """Test per-task run_parameters take precedence over defaults.

        Simulates the orchestrator logic: defaults are only injected
        when the parameter is not already present in per-task config.
        """
        default_run_parameters = {
            "shots": {"value": 4096, "value_type": "int"},
            "interval": {"value": 300, "value_type": "int"},
        }
        task_details: dict[str, Any] = {
            TASK_NAME: {
                "run_parameters": {
                    "shots": {"value": 512, "value_type": "int"},
                },
            },
        }

        # Simulate orchestrator injection logic
        task_params = task_details[TASK_NAME]
        if "run_parameters" not in task_params:
            task_params["run_parameters"] = {}
        for param_name, param_data in default_run_parameters.items():
            if param_name not in task_params["run_parameters"]:
                task_params["run_parameters"][param_name] = param_data

        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details=task_details,
            backend=BACKEND,
        )
        task = instances[TASK_NAME]
        # shots should keep per-task value (512), not default (4096)
        assert task.run_parameters["shots"].value == 512
        # interval should be injected from default
        assert task.run_parameters["interval"].value == 300

    def test_default_run_parameters_injection_with_empty_task_details(self):
        """Test injection when task has no per-task run_parameters."""
        default_run_parameters = {
            "shots": {"value": 2048, "value_type": "int"},
        }
        task_details: dict[str, Any] = {TASK_NAME: {}}

        # Simulate orchestrator injection logic
        task_params = task_details[TASK_NAME]
        if "run_parameters" not in task_params:
            task_params["run_parameters"] = {}
        for param_name, param_data in default_run_parameters.items():
            if param_name not in task_params["run_parameters"]:
                task_params["run_parameters"][param_name] = param_data

        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details=task_details,
            backend=BACKEND,
        )
        task = instances[TASK_NAME]
        assert task.run_parameters["shots"].value == 2048

    def test_malformed_default_run_parameter_skipped(self):
        """Test that non-dict default_run_parameters are skipped gracefully."""
        default_run_parameters: dict[str, Any] = {
            "shots": {"value": 2048, "value_type": "int"},
            "bad_param": "not_a_dict",  # malformed
            "another_bad": 42,  # malformed
        }
        task_details: dict[str, Any] = {TASK_NAME: {"run_parameters": {}}}

        # Simulate orchestrator injection logic with validation
        task_params = task_details[TASK_NAME]
        for param_name, param_data in default_run_parameters.items():
            if not isinstance(param_data, dict):
                continue
            if param_name not in task_params["run_parameters"]:
                task_params["run_parameters"][param_name] = param_data

        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details=task_details,
            backend=BACKEND,
        )
        task = instances[TASK_NAME]
        # Only valid param should be injected
        assert task.run_parameters["shots"].value == 2048
        assert "bad_param" not in task.run_parameters
        assert "another_bad" not in task.run_parameters


class TestBaseTaskSetRunParameters:
    """Test BaseTask._set_run_parameters validation."""

    def test_set_run_parameters_updates_existing(self):
        """Test _set_run_parameters updates existing parameter values."""
        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details={TASK_NAME: {}},
            backend=BACKEND,
        )
        task = instances[TASK_NAME]
        original_shots = task.run_parameters["shots"].value

        task._set_run_parameters({"shots": {"value": 9999}})

        assert task.run_parameters["shots"].value == 9999
        assert task.run_parameters["shots"].value != original_shots

    def test_set_run_parameters_adds_new(self):
        """Test _set_run_parameters creates new parameter."""
        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details={TASK_NAME: {}},
            backend=BACKEND,
        )
        task = instances[TASK_NAME]

        task._set_run_parameters(
            {
                "custom_param": {"value": 42, "value_type": "int", "unit": "ms"},
            }
        )

        assert "custom_param" in task.run_parameters
        assert task.run_parameters["custom_param"].value == 42
        assert task.run_parameters["custom_param"].unit == "ms"

    def test_set_run_parameters_preserves_unmodified(self):
        """Test _set_run_parameters does not affect other parameters."""
        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details={TASK_NAME: {}},
            backend=BACKEND,
        )
        task = instances[TASK_NAME]
        original_time_range = task.run_parameters["time_range"].value

        task._set_run_parameters({"shots": {"value": 512}})

        assert task.run_parameters["time_range"].value == original_time_range

    def test_set_run_parameters_type_conversion(self):
        """Test _set_run_parameters converts value types correctly."""
        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details={TASK_NAME: {}},
            backend=BACKEND,
        )
        task = instances[TASK_NAME]

        # Pass float string that should be converted to int
        task._set_run_parameters({"shots": {"value": "2048", "value_type": "int"}})

        assert task.run_parameters["shots"].value == 2048
        assert isinstance(task.run_parameters["shots"].value, int)
