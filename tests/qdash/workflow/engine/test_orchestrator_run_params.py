"""Tests for default_run_parameters injection in CalibOrchestrator."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock

import pytest

# Import fake tasks to trigger registration in BaseTask.registry
import qdash.workflow.calibtasks.fake  # noqa: F401
from qdash.common.config.calibration import DEFAULT_READOUT_DURATION
from qdash.workflow import sweep
from qdash.workflow.calibtasks.active_protocols import generate_task_instances
from qdash.workflow.calibtasks.base import BaseTask
from qdash.workflow.engine.config import CalibConfig
from qdash.workflow.engine.orchestrator import CalibOrchestrator
from qdash.workflow.engine.task_parameters import (
    normalize_task_parameters,
    task_parameters_from_run_parameters,
)

if TYPE_CHECKING:
    from qdash.workflow.engine.task.context import TaskContext

# FakeCheckRabi registers as "CheckRabi" with backend "fake"
TASK_NAME = "CheckRabi"
# CheckRabi also declares calibration inputs.
INPUT_TASK_NAME = "CheckRabi"
BACKEND = "fake"


def test_shared_readout_duration_configures_backend_session(monkeypatch: Any) -> None:
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name="fake",
        default_run_parameters={"readout_duration": 2048},
    )
    orchestrator = CalibOrchestrator(config)
    orchestrator._task_context = cast("TaskContext", SimpleNamespace(id="manager-1"))
    factory = MagicMock(return_value=SimpleNamespace(name="fake"))
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.create_backend", factory)

    orchestrator._create_backend()

    assert factory.call_args.kwargs["config"]["readout_duration"] == 2048.0


def test_missing_shared_readout_duration_uses_task_default_for_session(
    monkeypatch: Any,
) -> None:
    """The session starts from the value every declaring task defaults to.

    A pipeline spec or flow that sets no shared readout_duration must not leave
    the session on the Qubex default, which differs from the task default and
    makes every task that declares readout_duration fail its session check.
    """
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name="fake",
        default_run_parameters={"shots": 1024},
    )
    orchestrator = CalibOrchestrator(config)
    orchestrator._task_context = cast("TaskContext", SimpleNamespace(id="manager-1"))
    factory = MagicMock(return_value=SimpleNamespace(name="fake"))
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.create_backend", factory)

    orchestrator._create_backend()

    assert factory.call_args.kwargs["config"]["readout_duration"] == float(DEFAULT_READOUT_DURATION)


def test_coupling_qid_configures_coupling_backend_session(monkeypatch: Any) -> None:
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["32-33"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name="fake",
    )
    orchestrator = CalibOrchestrator(config)
    orchestrator._task_context = cast("TaskContext", SimpleNamespace(id="manager-1"))
    factory = MagicMock(return_value=SimpleNamespace(name="fake"))
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.create_backend", factory)

    orchestrator._create_backend()

    backend_config = factory.call_args.kwargs["config"]
    assert backend_config["task_type"] == "coupling"
    assert backend_config["qids"] == ["32-33"]


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

    def test_shared_defaults_reach_only_tasks_that_declare_them(self):
        """A flow's shared default for another task's parameter is not recorded on this task."""
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
            default_run_parameters={
                "shots": {"value": 4096, "value_type": "int"},
                # Pulse durations a fine-tune flow shares for its pulse tasks.
                "hpi_duration": {"value": 32, "value_type": "int"},
                "drag_hpi_duration": {"value": 16, "value_type": "int"},
            },
        )
        orchestrator = CalibOrchestrator(config)

        task = orchestrator._create_task_instance(TASK_NAME, None)

        assert task.run_parameters["shots"].value == 4096
        assert "hpi_duration" not in task.run_parameters
        assert "drag_hpi_duration" not in task.run_parameters


def _config(**kwargs: Any) -> CalibConfig:
    return CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name=BACKEND,
        **kwargs,
    )


class TestTaskRunParameterInjection:
    """Test task-specific parameters separately from shared defaults."""

    def test_task_parameters_have_explicit_precedence(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(
                default_run_parameters={
                    "shots": {"value": 4096, "value_type": "int"},
                    "readout_duration": {"value": 7, "value_type": "float"},
                    TASK_NAME: {
                        "shots": {"value": 2048, "value_type": "int"},
                        "time_range": {"value": (0, 601, 12), "value_type": "range"},
                        "interval": {"value": 8, "value_type": "int"},
                    },
                },
                task_parameters=normalize_task_parameters(
                    {
                        TASK_NAME: {
                            "run": {
                                "shots": {"value": 1024, "value_type": "int"},
                                "time_range": {"value": (0, 501, 10), "value_type": "range"},
                            }
                        }
                    }
                ),
            )
        )

        task = orchestrator._create_task_instance(
            TASK_NAME,
            {"run": {"shots": {"value": 512, "value_type": "int"}}},
        )

        assert task.run_parameters["shots"].value == 512
        assert task.run_parameters["time_range"].value == (0, 501, 10)
        # Legacy per-task and shared entries still reach the declared names.
        assert task.run_parameters["interval"].value == 8
        assert task.run_parameters["readout_duration"].value == 7

    def test_plain_shared_default_overrides_task_default(self) -> None:
        orchestrator = CalibOrchestrator(_config(default_run_parameters={"shots": 4096}))

        task = orchestrator._create_task_instance(TASK_NAME, None)

        assert task.run_parameters["shots"].value == 4096

    def test_update_policy_is_not_injected_as_a_run_parameter(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(
                task_parameters=task_parameters_from_run_parameters(
                    {
                        TASK_NAME: {
                            "shots": {"value": 1024, "value_type": "int"},
                            "update_calibration_parameters": False,
                        }
                    }
                ),
            )
        )

        task = orchestrator._create_task_instance(TASK_NAME, None)

        assert task.run_parameters["shots"].value == 1024
        assert "update_calibration_parameters" not in task.run_parameters

    def test_call_parameters_are_not_mutated(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(default_run_parameters={"shots": {"value": 4096, "value_type": "int"}})
        )
        parameters: dict[str, Any] = {"run": {}}

        orchestrator._create_task_instance(TASK_NAME, parameters)

        assert parameters == {"run": {}}

    def test_explicit_run_values_are_recorded_as_run_overrides(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(
                default_run_parameters={"interval": {"value": 8, "value_type": "int"}},
                task_parameters=normalize_task_parameters({TASK_NAME: {"run": {"shots": 1024}}}),
            )
        )

        task = orchestrator._create_task_instance(
            TASK_NAME,
            normalize_task_parameters({TASK_NAME: {"run": {"time_range": sweep.range(0, 101, 4)}}})[
                TASK_NAME
            ],
        )

        # Shared defaults are not explicit, so a re-execution snapshot keeps its own values.
        assert task.run_overrides == {"shots": 1024, "time_range": (0, 101, 4)}

    def test_undeclared_task_run_parameter_is_rejected(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(task_parameters=normalize_task_parameters({TASK_NAME: {"run": {"shotz": 1}}}))
        )

        with pytest.raises(ValueError, match="does not declare run parameter 'shotz'"):
            orchestrator._create_task_instance(TASK_NAME, None)

    def test_calibration_input_under_run_is_rejected_with_guidance(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(
                task_parameters=normalize_task_parameters(
                    {INPUT_TASK_NAME: {"run": {"control_frequency": {"value": 5.0}}}}
                )
            )
        )

        with pytest.raises(
            ValueError, match="calibration input of CheckRabi; set it under 'input'"
        ):
            orchestrator._create_task_instance(INPUT_TASK_NAME, None)

    def test_unknown_parameters_key_is_rejected(self) -> None:
        orchestrator = CalibOrchestrator(_config())

        with pytest.raises(ValueError, match="unknown keys"):
            orchestrator._create_task_instance(TASK_NAME, {"shots": 1})

    def test_array_run_value_rejects_string(self) -> None:
        orchestrator = CalibOrchestrator(_config())

        with pytest.raises(ValueError, match="requires a tuple/list of 3 values"):
            orchestrator._create_task_instance(TASK_NAME, {"run": {"time_range": "[0, 101, 4]"}})

    def test_sweep_constructor_may_differ_from_declared_run_type(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(
                task_parameters=normalize_task_parameters(
                    {TASK_NAME: {"run": {"time_range": sweep.linspace(0, 100, 11)}}}
                )
            )
        )

        task = orchestrator._create_task_instance(TASK_NAME, None)

        assert task.run_parameters["time_range"].value_type == "np.linspace"
        assert list(task.run_parameters["time_range"].get_value()) == list(range(0, 101, 10))

    def test_sweep_for_scalar_run_parameter_is_rejected(self) -> None:
        orchestrator = CalibOrchestrator(_config())

        with pytest.raises(ValueError, match=r"shots declares 'int' and cannot take"):
            orchestrator._create_task_instance(
                TASK_NAME, {"run": {"shots": {"value": [0, 1, 2], "value_type": "np.linspace"}}}
            )


class TestTaskInputOverrides:
    """Test task-scoped calibration input overrides."""

    def test_task_parameters_input_reaches_task_input_overrides(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(
                task_parameters=normalize_task_parameters(
                    {INPUT_TASK_NAME: {"input": {"control_frequency": 5.1}}}
                )
            )
        )

        task = orchestrator._create_task_instance(INPUT_TASK_NAME, None)

        assert task.input_overrides == {"control_frequency": 5.1}

    def test_call_parameters_input_takes_precedence(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(
                task_parameters=normalize_task_parameters(
                    {
                        INPUT_TASK_NAME: {
                            "input": {"control_frequency": 5.1, "control_amplitude": 0.2}
                        }
                    }
                )
            )
        )

        task = orchestrator._create_task_instance(
            INPUT_TASK_NAME,
            {"input": {"control_frequency": {"value": "5.3"}}},
        )

        assert task.input_overrides == {"control_frequency": 5.3, "control_amplitude": 0.2}

    def test_run_parameter_under_input_is_rejected_with_guidance(self) -> None:
        orchestrator = CalibOrchestrator(
            _config(task_parameters=normalize_task_parameters({TASK_NAME: {"input": {"shots": 1}}}))
        )

        with pytest.raises(ValueError, match="run parameter of CheckRabi; set it under 'run'"):
            orchestrator._create_task_instance(TASK_NAME, None)

    def test_forbidden_input_override_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        task_class = BaseTask.registry[BACKEND][INPUT_TASK_NAME]
        spec = dict(task_class.input_spec)
        spec["control_frequency"] = spec["control_frequency"].model_copy(
            update={"user_override": "forbidden"}
        )
        monkeypatch.setattr(task_class, "input_spec", spec)
        orchestrator = CalibOrchestrator(
            _config(
                task_parameters=normalize_task_parameters(
                    {INPUT_TASK_NAME: {"input": {"control_frequency": 5.1}}}
                )
            )
        )

        with pytest.raises(ValueError, match="does not allow user overrides"):
            orchestrator._create_task_instance(INPUT_TASK_NAME, None)


class TestTaskCalibrationParameterUpdates:
    """Test task-level calibration parameter update policy."""

    def test_workflow_defaults_to_persisting_task_outputs(self) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
        )
        orchestrator = CalibOrchestrator(config)

        assert orchestrator._should_update_calibration_parameters(TASK_NAME, None) is True

    def test_call_parameters_can_disable_calibration_parameter_updates(self) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
        )
        orchestrator = CalibOrchestrator(config)

        update_parameters = orchestrator._should_update_calibration_parameters(
            TASK_NAME,
            {"update_calibration_parameters": False},
        )

        assert update_parameters is False

    def test_task_parameters_can_disable_calibration_parameter_updates(self) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
            task_parameters=normalize_task_parameters(
                {TASK_NAME: {"update_calibration_parameters": False}}
            ),
        )
        orchestrator = CalibOrchestrator(config)

        assert orchestrator._should_update_calibration_parameters(TASK_NAME, None) is False

    def test_call_parameters_override_task_parameter_policy(self) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
            task_parameters=normalize_task_parameters(
                {TASK_NAME: {"update_calibration_parameters": False}}
            ),
        )
        orchestrator = CalibOrchestrator(config)

        update_parameters = orchestrator._should_update_calibration_parameters(
            TASK_NAME,
            {"update_calibration_parameters": True},
        )

        assert update_parameters is True

    def test_call_parameters_override_measurement_only_session_default(self) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
            persist_output_parameters=False,
        )
        orchestrator = CalibOrchestrator(config)

        update_parameters = orchestrator._should_update_calibration_parameters(
            TASK_NAME,
            {"update_calibration_parameters": True},
        )

        assert update_parameters is True

    def test_calibration_parameter_update_setting_requires_boolean(self) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
        )
        orchestrator = CalibOrchestrator(config)

        with pytest.raises(ValueError, match="must be a boolean"):
            orchestrator._should_update_calibration_parameters(
                TASK_NAME,
                {"update_calibration_parameters": "false"},
            )

    def test_run_task_passes_task_output_persistence_to_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
            task_parameters=normalize_task_parameters(
                {TASK_NAME: {"update_calibration_parameters": False}}
            ),
        )
        orchestrator = CalibOrchestrator(config)
        task = SimpleNamespace(get_task_type=lambda: "qubit")
        execution_context = SimpleNamespace()
        executed_context = SimpleNamespace()
        create_task = MagicMock(return_value=task)
        ensure_task = MagicMock()
        prepare_context = MagicMock(return_value=execution_context)
        run_task = MagicMock(return_value=executed_context)
        merge_results = MagicMock(return_value={})
        monkeypatch.setattr(orchestrator, "_create_task_instance", create_task)
        monkeypatch.setattr(orchestrator, "_ensure_task_in_workflow", ensure_task)
        monkeypatch.setattr(orchestrator, "_prepare_execution_context", prepare_context)
        monkeypatch.setattr(orchestrator, "_run_prefect_task", run_task)
        monkeypatch.setattr(orchestrator, "_merge_and_extract_results", merge_results)

        orchestrator.run_task(TASK_NAME, "0")

        prepare_context.assert_called_once_with(
            "0",
            None,
            persist_output_parameters=False,
        )
        merge_results.assert_called_once_with(
            executed_context,
            TASK_NAME,
            "qubit",
            "0",
            update_calibration_parameters=False,
        )

    def test_run_task_batch_passes_task_output_persistence_to_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = CalibConfig(
            username="alice",
            chip_id="chip-1",
            qids=["0", "1"],
            execution_id="exec-1",
            project_id="project-1",
            backend_name=BACKEND,
        )
        orchestrator = CalibOrchestrator(config)
        task = SimpleNamespace(get_task_type=lambda: "qubit")
        execution_context = SimpleNamespace()
        executed_context = SimpleNamespace()
        create_task = MagicMock(return_value=task)
        ensure_task = MagicMock()
        prepare_context = MagicMock(return_value=execution_context)
        run_task = MagicMock(return_value=executed_context)
        merge_results = MagicMock(return_value={})
        monkeypatch.setattr(orchestrator, "_create_task_instance", create_task)
        monkeypatch.setattr(orchestrator, "_ensure_task_in_workflow", ensure_task)
        monkeypatch.setattr(orchestrator, "_prepare_batch_execution_context", prepare_context)
        monkeypatch.setattr(orchestrator, "_run_prefect_batch_task", run_task)
        monkeypatch.setattr(orchestrator, "_merge_and_extract_batch_results", merge_results)

        orchestrator.run_task_batch(
            TASK_NAME,
            ["0", "1"],
            {"update_calibration_parameters": False},
        )

        prepare_context.assert_called_once_with(
            ["0", "1"],
            None,
            persist_output_parameters=False,
        )
        merge_results.assert_called_once_with(
            executed_context,
            TASK_NAME,
            "qubit",
            ["0", "1"],
            update_calibration_parameters=False,
        )


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

    def test_set_run_parameters_ignores_undeclared_names(self):
        """A name the task does not declare in run_spec is not recorded.

        The task reads run parameters by name, so an undeclared value would
        never be used; recording it would misstate the task's settings.
        """
        instances = generate_task_instances(
            task_names=[TASK_NAME],
            task_details={TASK_NAME: {}},
            backend=BACKEND,
        )
        task = instances[TASK_NAME]
        declared = set(task.run_parameters)

        task._set_run_parameters(
            {
                "custom_param": {"value": 42, "value_type": "int", "unit": "ms"},
                "shots": {"value": 128},
            }
        )

        assert set(task.run_parameters) == declared
        assert "custom_param" not in task.run_parameters
        assert task.run_parameters["shots"].value == 128

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


def _write_two_system_tree(root: Any) -> None:
    import yaml

    config = root / "config"
    config.mkdir(parents=True)
    (config / "chip.yaml").write_text(yaml.safe_dump({"chip-1": {"n_qubits": 16}}))
    (config / "system.yaml").write_text(
        yaml.safe_dump(
            {
                "chip-1": {"chip_id": "chip-1", "backend": "quel1"},
                "chip-1-quel3": {"chip_id": "chip-1", "backend": "quel3"},
            }
        )
    )
    rows = lambda *ids: [{"mux": m, "ctrl": [f"C{m}-0"], "read_out": f"R{m}-0"} for m in ids]  # noqa: E731
    (config / "wiring.yaml").write_text(
        yaml.safe_dump({"chip-1": rows(0, 1), "chip-1-quel3": rows(2, 3)})
    )


def _orchestrator(monkeypatch: Any, qids: list[str]) -> tuple[CalibOrchestrator, MagicMock]:
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=qids,
        execution_id="exec-1",
        project_id="project-1",
        backend_name="fake",
    )
    orchestrator = CalibOrchestrator(config)
    orchestrator._task_context = cast("TaskContext", SimpleNamespace(id="manager-1"))
    factory = MagicMock(return_value=SimpleNamespace(name="fake"))
    monkeypatch.setattr("qdash.workflow.engine.orchestrator.create_backend", factory)
    return orchestrator, factory


def test_session_records_the_single_system_of_its_targets(monkeypatch: Any, tmp_path: Any) -> None:
    _write_two_system_tree(tmp_path)
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    orchestrator, factory = _orchestrator(monkeypatch, ["8", "10-11"])

    orchestrator._create_backend()

    session_config = factory.call_args.kwargs["config"]
    assert session_config["system_ids"] == ["chip-1-quel3"]
    assert session_config["system_id"] == "chip-1-quel3"
    assert (orchestrator.config.note or {})["system_ids"] == ["chip-1-quel3"]


def test_owner_session_spanning_systems_gets_no_single_system(
    monkeypatch: Any, tmp_path: Any
) -> None:
    _write_two_system_tree(tmp_path)
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    orchestrator, factory = _orchestrator(monkeypatch, ["0", "8"])

    orchestrator._create_backend()

    session_config = factory.call_args.kwargs["config"]
    assert session_config["system_ids"] == ["chip-1", "chip-1-quel3"]
    assert "system_id" not in session_config


def test_unreadable_tree_falls_back_to_the_chip_as_system(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setattr(
        "qdash.common.config.qubex_layout.resolve_config_base_path", lambda: tmp_path
    )
    orchestrator, factory = _orchestrator(monkeypatch, ["0"])

    orchestrator._create_backend()

    assert factory.call_args.kwargs["config"]["system_id"] == "chip-1"
