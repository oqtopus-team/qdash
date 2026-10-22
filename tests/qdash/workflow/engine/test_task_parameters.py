"""Tests for task-scoped workflow parameters."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.workflow import sweep
from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_adaptive_chevron import (
    CheckAdaptiveChevron,
)
from qdash.workflow.engine.config import CalibConfig
from qdash.workflow.engine.orchestrator import CalibOrchestrator
from qdash.workflow.engine.task.executor import TaskExecutor
from qdash.workflow.engine.task_parameters import (
    merge_task_parameters,
    normalize_default_run_parameters,
    normalize_task_parameters,
    resolve_task_parameters,
    task_parameters_from_run_parameters,
    task_settings_from_task_details,
    validate_task_names,
)
from qdash.workflow.service.calib_service import CalibService


class TestNormalizeTaskParameters:
    def test_fills_sections_and_normalizes_value_forms(self) -> None:
        normalized = normalize_task_parameters(
            {
                "CheckRabi": {
                    "run": {"shots": 256, "interval": {"value": 1024, "value_type": "int"}},
                    "input": {"control_amplitude": {"value": 0.05}},
                },
                "CheckT1": {"update_calibration_parameters": False},
            }
        )

        assert normalized == {
            "CheckRabi": {
                "run": {
                    "shots": {"value": 256},
                    "interval": {"value": 1024, "value_type": "int"},
                },
                "input": {"control_amplitude": 0.05},
            },
            "CheckT1": {"run": {}, "input": {}, "update_calibration_parameters": False},
        }

    def test_rejects_flat_parameter_names(self) -> None:
        with pytest.raises(ValueError, match=r"unknown keys \['shots'\]"):
            normalize_task_parameters({"CheckRabi": {"shots": {"value": 256}}})

    def test_rejects_non_boolean_update_policy(self) -> None:
        with pytest.raises(ValueError, match="must be a boolean"):
            normalize_task_parameters({"CheckRabi": {"update_calibration_parameters": "no"}})

    def test_rejects_input_without_value(self) -> None:
        with pytest.raises(ValueError, match="needs a value"):
            normalize_task_parameters({"CheckRabi": {"input": {"control_amplitude": None}}})

    def test_rejects_sweep_as_calibration_input(self) -> None:
        with pytest.raises(ValueError, match="put generated experiment ranges under 'run'"):
            normalize_task_parameters(
                {"CheckRabi": {"input": {"control_amplitude": sweep.linspace(0, 1, 5)}}}
            )

    def test_returns_independent_copy(self) -> None:
        source: dict[str, Any] = {"CheckRabi": {"run": {"shots": {"value": 256}}}}

        normalized = normalize_task_parameters(source)
        normalized["CheckRabi"]["run"]["shots"]["value"] = 1

        assert source["CheckRabi"]["run"]["shots"]["value"] == 256

    @pytest.mark.parametrize(
        ("declaration", "expected_type", "expected_value"),
        [
            (sweep.linspace(0, 1, 5), "np.linspace", (0, 1, 5)),
            (sweep.logspace(2, 6, 51), "np.logspace", (2, 6, 51)),
            (sweep.arange(0, 10, 2), "np.arange", (0, 10, 2)),
            (sweep.range(0, 10, 2), "range", (0, 10, 2)),
        ],
    )
    def test_normalizes_declarative_sweep(
        self,
        declaration: Any,
        expected_type: str,
        expected_value: tuple[int | float, int | float, int | float],
    ) -> None:
        normalized = normalize_task_parameters({"CheckRabi": {"run": {"time_range": declaration}}})

        assert normalized["CheckRabi"]["run"]["time_range"] == {
            "value": expected_value,
            "value_type": expected_type,
        }


class TestNormalizeDefaultRunParameters:
    def test_normalizes_plain_values_and_sweeps(self) -> None:
        normalized = normalize_default_run_parameters(
            {"shots": 1024, "time_range": sweep.range(0, 101, 4)}
        )

        assert normalized == {
            "shots": {"value": 1024},
            "time_range": {"value": (0, 101, 4), "value_type": "range"},
        }

    def test_preserves_and_normalizes_legacy_task_nested_defaults(self) -> None:
        normalized = normalize_default_run_parameters(
            {
                "CheckRabi": {
                    "shots": 1024,
                    "time_range": {"value": (0, 101, 4), "value_type": "range"},
                    "update_calibration_parameters": False,
                }
            }
        )

        assert normalized == {
            "CheckRabi": {
                "shots": {"value": 1024},
                "time_range": {"value": (0, 101, 4), "value_type": "range"},
                "update_calibration_parameters": False,
            }
        }


class TestLegacyTaskRunParameters:
    def test_flat_form_becomes_run_section(self) -> None:
        converted = task_parameters_from_run_parameters(
            {
                "CheckRabi": {
                    "shots": {"value": 256, "value_type": "int"},
                    "update_calibration_parameters": False,
                }
            }
        )

        assert converted == {
            "CheckRabi": {
                "run": {"shots": {"value": 256, "value_type": "int"}},
                "input": {},
                "update_calibration_parameters": False,
            }
        }

    def test_resolve_warns_and_lets_task_parameters_win(self) -> None:
        with pytest.warns(DeprecationWarning, match="task_run_parameters is deprecated"):
            resolved = resolve_task_parameters(
                {"CheckRabi": {"run": {"shots": 512}, "input": {"control_amplitude": 0.05}}},
                {"CheckRabi": {"shots": {"value": 256}, "interval": {"value": 8}}},
            )

        assert resolved == {
            "CheckRabi": {
                "run": {"shots": {"value": 512}, "interval": {"value": 8}},
                "input": {"control_amplitude": 0.05},
            }
        }

    def test_resolve_without_legacy_form_does_not_warn(self, recwarn: Any) -> None:
        resolve_task_parameters({"CheckRabi": {"run": {"shots": 512}}}, None)

        assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]


class TestLegacyTaskDetails:
    def test_legacy_keys_map_to_run_and_input(self) -> None:
        settings = task_settings_from_task_details(
            "CheckRabi",
            {
                "CheckRabi": {
                    "input_parameters": {"interval": {"value": 8}},
                    "run_parameters": {"shots": {"value": 256}},
                    "calibration_inputs": {"control_amplitude": {"value": 0.05, "unit": "a.u."}},
                    "update_calibration_parameters": False,
                }
            },
        )

        assert settings == {
            "run": {"interval": {"value": 8}, "shots": {"value": 256}},
            "input": {"control_amplitude": 0.05},
            "update_calibration_parameters": False,
        }

    def test_unknown_key_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown keys"):
            task_settings_from_task_details("CheckRabi", {"CheckRabi": {"shots": 1}})

    def test_execute_task_warns_and_lets_parameters_win(self) -> None:
        with pytest.warns(DeprecationWarning, match="task_details is deprecated"):
            settings = CalibService._call_settings(
                "CheckRabi",
                {"CheckRabi": {"run_parameters": {"shots": {"value": 256}}}},
                {"run": {"shots": 512}, "input": {"control_amplitude": 0.05}},
            )

        assert settings == {
            "run": {"shots": {"value": 512}},
            "input": {"control_amplitude": 0.05},
        }

    def test_legacy_input_parameters_rejects_calibration_input_with_guidance(self) -> None:
        """The legacy key remains a Run alias and reports misplaced Inputs explicitly."""
        with pytest.warns(DeprecationWarning, match="task_details is deprecated"):
            settings = CalibService._call_settings(
                "CheckAdaptiveChevron",
                {
                    "CheckAdaptiveChevron": {
                        "input_parameters": {"coarse_control_amplitude": {"value": 0.05}}
                    }
                },
                None,
            )
        orchestrator = CalibOrchestrator(
            CalibConfig(
                username="alice",
                chip_id="chip-1",
                qids=["0"],
                execution_id="exec-1",
                project_id="project-1",
                backend_name="qubex",
            )
        )

        with pytest.raises(
            ValueError,
            match=(
                "calibration input of CheckAdaptiveChevron; set it under 'input' instead of 'run'"
            ),
        ):
            orchestrator._create_task_instance("CheckAdaptiveChevron", settings)


class TestValidateTaskNames:
    def test_accepts_registered_tasks(self) -> None:
        validate_task_names({"CheckRabi": {}, "CheckAdaptiveChevron": {}}, "qubex")

    def test_rejects_misspelled_task_with_suggestion(self) -> None:
        with pytest.raises(ValueError, match=r"'CheckRabbi' \(did you mean 'CheckRabi'\?\)"):
            validate_task_names({"CheckRabbi": {"run": {"shots": 256}}}, "qubex")

    def test_rejects_unknown_task_without_close_match(self) -> None:
        with pytest.raises(ValueError, match=r"not registered for backend 'qubex': 'Zzz'$"):
            validate_task_names({"Zzz": {}}, "qubex")

    def test_calib_service_rejects_misspelled_task_before_starting(self) -> None:
        with pytest.raises(ValueError, match="did you mean 'CheckRabi'"):
            CalibService(
                "alice",
                "chip-1",
                backend_name="qubex",
                project_id="project-1",
                task_parameters={"CheckRabbi": {"run": {"shots": 256}}},
            )


def test_merge_later_layer_wins_per_parameter() -> None:
    merged = merge_task_parameters(
        normalize_task_parameters(
            {"CheckRabi": {"input": {"control_amplitude": 0.1, "control_frequency": 5.0}}}
        ),
        normalize_task_parameters({"CheckRabi": {"input": {"control_amplitude": 0.2}}}),
    )

    assert merged["CheckRabi"]["input"] == {"control_amplitude": 0.2, "control_frequency": 5.0}


def test_coarse_control_amplitude_override_survives_database_resolution() -> None:
    """Regression: a workflow override of coarse_control_amplitude reached run()."""
    config = CalibConfig(
        username="alice",
        chip_id="chip-1",
        qids=["0"],
        execution_id="exec-1",
        project_id="project-1",
        backend_name="qubex",
        task_parameters=normalize_task_parameters(
            {"CheckAdaptiveChevron": {"input": {"coarse_control_amplitude": 0.05}}}
        ),
    )
    task = CalibOrchestrator(config)._create_task_instance("CheckAdaptiveChevron", None)
    assert isinstance(task, CheckAdaptiveChevron)

    # What QubexTask.preprocess does for a fresh execution.
    calibration_data = {
        "coarse_control_amplitude": {"value": 0.2},
        "control_frequency": {"value": 7.0},
        "readout_frequency": {"value": 10.0},
        "readout_amplitude": {"value": 0.1},
    }
    task._populate_parameters({"": [calibration_data], "self": [calibration_data]})
    assert task.input_parameters["coarse_control_amplitude"].value == 0.2

    executor = TaskExecutor(
        state_manager=MagicMock(),
        calib_dir="/tmp/calib",
        execution_id="exec-1",
        task_manager_id="tm-1",
    )
    executor._apply_input_overrides(task, "CheckAdaptiveChevron", "qubit", "0")
    executor._validate_effective_inputs(task)

    assert task.input_parameters["coarse_control_amplitude"].value == 0.05
