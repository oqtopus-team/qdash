"""Tests for default_run_parameters injection in CalibOrchestrator."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import pytest

# Import fake tasks to trigger registration in BaseTask.registry
import qdash.workflow.calibtasks.fake  # noqa: F401
from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.engine.config import CalibConfig
from qdash.workflow.engine.orchestrator import CalibOrchestrator

if TYPE_CHECKING:
    from qdash.workflow.engine.task.context import TaskContext

# FakeCheckRabi registers as "CheckRabi" with backend "fake"
TASK_NAME = "CheckRabi"
BACKEND = "fake"


def test_shared_readout_duration_configures_backend_session(monkeypatch: Any) -> None:
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name="fake",
        default_run_parameters={"readout_duration": {"value": 2048, "value_type": "int"}},
    )
    orchestrator = CalibOrchestrator(config)
    orchestrator._task_context = cast("TaskContext", SimpleNamespace(id="manager-1"))
    factory = MagicMock(return_value=SimpleNamespace(name="fake"))
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.create_backend", factory)

    orchestrator._create_backend()

    assert factory.call_args.kwargs["config"]["readout_duration"] == 2048.0


@pytest.mark.parametrize("readout_duration", [0, -1, float("nan"), float("inf")])
def test_invalid_shared_readout_duration_is_rejected_before_backend_creation(
    monkeypatch: Any, readout_duration: float
) -> None:
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name="fake",
        default_run_parameters={
            "readout_duration": {"value": readout_duration, "value_type": "float"}
        },
    )
    orchestrator = CalibOrchestrator(config)
    orchestrator._task_context = cast("TaskContext", SimpleNamespace(id="manager-1"))
    factory = MagicMock()
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.create_backend", factory)

    with pytest.raises(ValueError, match="readout_duration must be finite and positive"):
        orchestrator._create_backend()

    factory.assert_not_called()


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


class TestTaskRunParameterInjection:
    """Test task-specific parameters separately from shared defaults."""

    def test_task_run_parameters_have_explicit_precedence(self) -> None:
        config = cast(
            "CalibConfig",
            SimpleNamespace(
                backend_name=BACKEND,
                default_run_parameters={
                    "shots": {"value": 4096, "value_type": "int"},
                    "shared_only": {"value": 7, "value_type": "int"},
                    TASK_NAME: {
                        "shots": {"value": 2048, "value_type": "int"},
                        "time_range": {"value": (0, 601, 12), "value_type": "range"},
                        "legacy_only": {"value": 8, "value_type": "int"},
                    },
                },
                task_run_parameters={
                    TASK_NAME: {
                        "shots": {"value": 1024, "value_type": "int"},
                        "time_range": {"value": (0, 501, 10), "value_type": "range"},
                    }
                },
            ),
        )
        orchestrator = CalibOrchestrator(config)

        task = orchestrator._create_task_instance(
            TASK_NAME,
            {TASK_NAME: {"run_parameters": {"shots": {"value": 512, "value_type": "int"}}}},
        )

        assert task.run_parameters["shots"].value == 512
        assert task.run_parameters["time_range"].value == (0, 501, 10)
        assert task.run_parameters["legacy_only"].value == 8
        assert task.run_parameters["shared_only"].value == 7


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
