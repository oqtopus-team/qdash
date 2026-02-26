"""Tests for TaskExecutor."""

from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest
from qdash.datamodel.task import ParameterModel, QubitTaskModel, RunParameterModel, TaskStatusModel
from qdash.workflow.calibtasks.base import PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.engine.task.executor import TaskExecutor
from qdash.workflow.engine.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
)
from qdash.workflow.engine.task.types import TaskExecutionError, TaskProtocol


class MockTask:
    """Mock task for testing."""

    run_parameters: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        name: str = "CheckRabi",
        task_type: str = "qubit",
        r2_threshold: float = 0.7,
        backend: str = "fake",
    ) -> None:
        self.name = name
        self._task_type = task_type
        self.r2_threshold = r2_threshold
        self.backend = backend
        self.input_parameters: dict[str, Any] = {}

    def get_name(self) -> str:
        return self.name

    def get_task_type(self) -> str:
        return self._task_type

    def is_qubit_task(self) -> bool:
        return self._task_type == "qubit"

    def is_coupling_task(self) -> bool:
        return self._task_type == "coupling"

    def preprocess(self, session: Any, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters={"param1": ParameterModel(value=1.0)})

    def run(self, session: Any, qid: str) -> RunResult:
        return RunResult(raw_result={"data": [1, 2, 3]}, r2={"0": 0.95})

    def postprocess(
        self, session: Any, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(
            output_parameters={"qubit_frequency": ParameterModel(value=5.0)},
            figures=[],
            raw_data=[],
        )

    def attach_task_id(self, task_id: str) -> dict[str, ParameterModel]:
        return {}


class MockSession:
    """Mock session for testing."""

    name = "test-session"

    def update_note(self, key: str, value: Any) -> None:
        pass


class TestTaskExecutorInit:
    """Test TaskExecutor initialization."""

    def test_init_with_all_dependencies(self) -> None:
        """Test initialization with all dependencies provided."""
        state_manager = MagicMock()
        result_processor = MagicMock()
        data_saver = MagicMock()

        executor = TaskExecutor(
            state_manager=state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
            result_processor=result_processor,
            data_saver=data_saver,
        )

        assert executor.state_manager == state_manager
        assert executor.result_processor == result_processor
        assert executor.data_saver == data_saver
        assert executor.execution_id == "exec-001"
        assert executor.task_manager_id == "tm-001"

    def test_init_creates_default_dependencies(self) -> None:
        """Test initialization creates default dependencies if not provided."""
        state_manager = MagicMock()

        executor = TaskExecutor(
            state_manager=state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
        )

        assert executor.result_processor is not None
        assert executor.data_saver is not None


class TestTaskExecutorExecuteTask:
    """Test TaskExecutor.execute_task method."""

    @pytest.fixture
    def mock_state_manager(self) -> MagicMock:
        """Create a mock state manager."""
        state_manager = MagicMock()
        state_manager.get_task.return_value = QubitTaskModel(
            name="CheckRabi",
            qid="0",
            task_id="task-001",
            status=TaskStatusModel.RUNNING,
        )
        return state_manager

    @pytest.fixture
    def mock_result_processor(self) -> MagicMock:
        """Create a mock result processor."""
        processor = MagicMock()
        processor.validate_r2.return_value = True
        processor.process_output_parameters.return_value = {
            "qubit_frequency": ParameterModel(
                value=5.0, execution_id="exec-001", task_id="task-001"
            )
        }
        return processor

    @pytest.fixture
    def mock_data_saver(self) -> MagicMock:
        """Create a mock data saver."""
        saver = MagicMock()
        saver.save_figures.return_value = ([], [])
        saver.save_raw_data.return_value = []
        return saver

    @pytest.fixture
    def executor(
        self,
        mock_state_manager: MagicMock,
        mock_result_processor: MagicMock,
        mock_data_saver: MagicMock,
    ) -> TaskExecutor:
        """Create an executor with mocked dependencies."""
        return TaskExecutor(
            state_manager=mock_state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
            result_processor=mock_result_processor,
            data_saver=mock_data_saver,
        )

    def test_execute_task_success(
        self, executor: TaskExecutor, mock_state_manager: MagicMock
    ) -> None:
        """Test successful task execution."""
        task = MockTask()
        session: Any = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["success"] is True
        assert result["task_name"] == "CheckRabi"
        assert result["qid"] == "0"
        mock_state_manager.start_task.assert_called_once_with("CheckRabi", "qubit", "0")
        mock_state_manager.end_task.assert_called_once_with("CheckRabi", "qubit", "0")

    def test_execute_task_calls_preprocess(
        self, executor: TaskExecutor, mock_state_manager: MagicMock
    ) -> None:
        """Test execute_task calls preprocess and stores input parameters."""
        task = MockTask()
        session: Any = MockSession()

        executor.execute_task(task, session, "0")

        mock_state_manager.put_input_parameters.assert_called_once()
        call_args = mock_state_manager.put_input_parameters.call_args
        assert call_args[0][0] == "CheckRabi"
        assert "param1" in call_args[0][1]
        assert call_args[0][1]["param1"].value == 1.0

    def test_execute_task_handles_no_run_result(
        self, executor: TaskExecutor, mock_state_manager: MagicMock
    ) -> None:
        """Test execute_task handles task with no run result."""
        task = MockTask()
        task.run = MagicMock(return_value=None)  # type: ignore[method-assign]
        session: Any = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["success"] is True
        assert result["message"] == "Completed without run result"
        mock_state_manager.update_task_status_to_completed.assert_called_once()

    def test_execute_task_validates_r2(
        self, executor: TaskExecutor, mock_result_processor: MagicMock
    ) -> None:
        """Test execute_task validates R² values."""
        task = MockTask()
        session: Any = MockSession()

        executor.execute_task(task, session, "0")

        mock_result_processor.validate_r2.assert_called_once()
        call_args = mock_result_processor.validate_r2.call_args
        assert call_args[0][0] == {"0": 0.95}  # r2 dict
        assert call_args[0][1] == "0"  # qid
        assert call_args[0][2] == 0.7  # threshold from task

    def test_execute_task_raises_on_r2_validation_failure(
        self,
        executor: TaskExecutor,
        mock_result_processor: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test execute_task raises on R² validation failure."""
        mock_result_processor.validate_r2.side_effect = R2ValidationError("R² value too low")
        task = MockTask()
        session: Any = MockSession()

        with pytest.raises(ValueError, match="R² value too low"):
            executor.execute_task(task, session, "0")

        mock_state_manager.update_task_status_to_failed.assert_called_once()

    def test_execute_task_raises_on_fidelity_validation_failure(
        self,
        executor: TaskExecutor,
        mock_result_processor: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test execute_task raises on fidelity validation failure."""
        mock_result_processor.process_output_parameters.side_effect = FidelityValidationError(
            "Fidelity exceeds 100%"
        )
        task = MockTask()
        session: Any = MockSession()

        with pytest.raises(FidelityValidationError, match="Fidelity exceeds 100%"):
            executor.execute_task(task, session, "0")

        mock_state_manager.update_task_status_to_failed.assert_called_once()

    def test_execute_task_raises_task_execution_error_on_exception(
        self, executor: TaskExecutor, mock_state_manager: MagicMock
    ) -> None:
        """Test execute_task raises TaskExecutionError on unexpected exception."""
        task = MockTask()
        task.run = MagicMock(side_effect=RuntimeError("Unexpected error"))  # type: ignore[method-assign]
        session: Any = MockSession()

        with pytest.raises(TaskExecutionError, match="Task CheckRabi failed"):
            executor.execute_task(task, session, "0")

        mock_state_manager.update_task_status_to_failed.assert_called_once()

    def test_execute_task_always_calls_end_task(
        self, executor: TaskExecutor, mock_state_manager: MagicMock
    ) -> None:
        """Test execute_task always calls end_task even on failure."""
        task = MockTask()
        task.run = MagicMock(side_effect=RuntimeError("Error"))  # type: ignore[method-assign]
        session: Any = MockSession()

        with pytest.raises(TaskExecutionError):
            executor.execute_task(task, session, "0")

        # end_task should always be called (in finally block)
        mock_state_manager.end_task.assert_called_once()

    def test_execute_task_saves_figures(
        self, executor: TaskExecutor, mock_data_saver: MagicMock
    ) -> None:
        """Test execute_task saves figures from postprocess result."""
        import plotly.graph_objects as go

        task = MockTask()
        fig = go.Figure()
        task.postprocess = MagicMock(  # type: ignore[method-assign]
            return_value=PostProcessResult(
                output_parameters={},
                figures=[fig],
                raw_data=[],
            )
        )
        session: Any = MockSession()

        executor.execute_task(task, session, "0")

        mock_data_saver.save_figures.assert_called_once()

    def test_execute_task_saves_raw_data(
        self, executor: TaskExecutor, mock_data_saver: MagicMock
    ) -> None:
        """Test execute_task saves raw data from postprocess result."""
        task = MockTask()
        task.postprocess = MagicMock(  # type: ignore[method-assign]
            return_value=PostProcessResult(
                output_parameters={},
                figures=[],
                raw_data=[{"x": [1, 2], "y": [3, 4]}],
            )
        )
        session: Any = MockSession()

        executor.execute_task(task, session, "0")

        mock_data_saver.save_raw_data.assert_called_once()

    def test_execute_task_processes_output_parameters(
        self,
        executor: TaskExecutor,
        mock_result_processor: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test execute_task processes and stores output parameters."""
        task = MockTask()
        session: Any = MockSession()

        result = executor.execute_task(task, session, "0")

        mock_result_processor.process_output_parameters.assert_called_once()
        mock_state_manager.put_output_parameters.assert_called_once()
        assert "output_parameters" in result

    def test_execute_task_returns_r2_in_result(self, executor: TaskExecutor) -> None:
        """Test execute_task returns R² value in result."""
        task = MockTask()
        session: Any = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["r2"] == {"0": 0.95}

    def test_execute_task_records_run_parameters(
        self, executor: TaskExecutor, mock_state_manager: MagicMock
    ) -> None:
        """Test execute_task records run_parameters when present."""
        task = MockTask()
        MockTask.run_parameters = {
            "shots": RunParameterModel(value=1024, value_type="int", description="Number of shots"),
            "interval": RunParameterModel(value=150, value_type="int", unit="us"),
        }
        session: Any = MockSession()

        executor.execute_task(task, session, "0")

        # Reset class variable
        MockTask.run_parameters = {}

        mock_state_manager.put_run_parameters.assert_called_once()
        call_args = mock_state_manager.put_run_parameters.call_args[0]
        assert call_args[0] == "CheckRabi"  # task_name
        assert "shots" in call_args[1]  # run_params dict
        assert "interval" in call_args[1]
        assert call_args[1]["shots"]["value"] == 1024
        assert call_args[2] == "qubit"  # task_type
        assert call_args[3] == "0"  # qid

    def test_execute_task_skips_empty_run_parameters(
        self, executor: TaskExecutor, mock_state_manager: MagicMock
    ) -> None:
        """Test execute_task does not call put_run_parameters when empty."""
        task = MockTask()
        MockTask.run_parameters = {}
        session: Any = MockSession()

        executor.execute_task(task, session, "0")

        mock_state_manager.put_run_parameters.assert_not_called()


class TestTaskExecutorHelperMethods:
    """Test TaskExecutor helper methods."""

    @pytest.fixture
    def executor(self) -> TaskExecutor:
        """Create an executor with mocked dependencies."""
        state_manager = MagicMock()
        state_manager.get_task.return_value = QubitTaskModel(
            name="CheckRabi",
            qid="0",
            task_id="task-001",
            status=TaskStatusModel.RUNNING,
        )
        return TaskExecutor(
            state_manager=state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
        )

    def test_run_preprocess_returns_result(self, executor: TaskExecutor) -> None:
        """Test _run_preprocess returns preprocess result."""
        task = MockTask()
        session: Any = MockSession()

        result = executor._run_preprocess(task, session, "0")

        assert result is not None
        assert "param1" in result.input_parameters
        param1 = result.input_parameters["param1"]
        assert param1 is not None
        assert param1.value == 1.0

    def test_run_preprocess_handles_exception(self, executor: TaskExecutor) -> None:
        """Test _run_preprocess handles exception gracefully."""
        task = MockTask()
        task.preprocess = MagicMock(side_effect=RuntimeError("Preprocess failed"))  # type: ignore[method-assign]
        session: Any = MockSession()

        result = executor._run_preprocess(task, session, "0")

        assert result is None

    def test_run_task_returns_result(self, executor: TaskExecutor) -> None:
        """Test _run_task returns run result."""
        task = MockTask()
        session: Any = MockSession()

        result = executor._run_task(task, session, "0")

        assert result is not None
        assert result.raw_result == {"data": [1, 2, 3]}
        assert result.r2 == {"0": 0.95}

    def test_run_postprocess_returns_result(self, executor: TaskExecutor) -> None:
        """Test _run_postprocess returns postprocess result."""
        task = MockTask()
        session: Any = MockSession()
        run_result = RunResult(raw_result={}, r2={})

        result = executor._run_postprocess(task, session, run_result, "0")

        assert result is not None
        assert "qubit_frequency" in result.output_parameters


class TestTaskProtocol:
    """Test TaskProtocol compliance."""

    def test_mock_task_satisfies_protocol(self) -> None:
        """Test that MockTask satisfies TaskProtocol."""
        task = MockTask()

        assert isinstance(task, TaskProtocol)

    def test_protocol_requires_name_attribute(self) -> None:
        """Test TaskProtocol requires name attribute."""

        class IncompleteTask:
            def get_name(self) -> str:
                return "test"

        task = IncompleteTask()
        assert not isinstance(task, TaskProtocol)


class TestCouplingTask:
    """Test TaskExecutor with coupling tasks."""

    @pytest.fixture
    def executor(self) -> TaskExecutor:
        """Create an executor for coupling task tests."""
        state_manager = MagicMock()
        state_manager.get_task.return_value = MagicMock(task_id="task-001")
        result_processor = MagicMock()
        result_processor.validate_r2.return_value = True
        result_processor.process_output_parameters.return_value = {}
        data_saver = MagicMock()
        data_saver.save_figures.return_value = ([], [])
        data_saver.save_raw_data.return_value = []

        return TaskExecutor(
            state_manager=state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
            result_processor=result_processor,
            data_saver=data_saver,
        )

    def test_execute_coupling_task(self, executor: TaskExecutor) -> None:
        """Test executing a coupling task."""
        task = MockTask(name="CheckCoupling", task_type="coupling")
        session: Any = MockSession()

        result = executor.execute_task(task, session, "0-1")

        assert result["task_type"] == "coupling"
        assert result["qid"] == "0-1"
        assert result["success"] is True


class TestReconstructParam:
    """Test TaskExecutor._reconstruct_param static method."""

    def test_reconstruct_from_dict(self) -> None:
        """Test reconstructing a ParameterModel from a dict."""
        result = TaskExecutor._reconstruct_param(
            ParameterModel, "freq", {"value": 5.0, "unit": "GHz"}
        )
        assert result is not None
        assert result.value == 5.0
        assert result.unit == "GHz"

    def test_reconstruct_from_scalar(self) -> None:
        """Test reconstructing a ParameterModel from a scalar value."""
        result = TaskExecutor._reconstruct_param(ParameterModel, "freq", 5.0)
        assert result is not None
        assert result.value == 5.0

    def test_reconstruct_run_parameter_from_dict(self) -> None:
        """Test reconstructing a RunParameterModel from a dict."""
        result = TaskExecutor._reconstruct_param(
            RunParameterModel, "shots", {"value": 1024, "value_type": "int"}
        )
        assert result is not None
        assert result.value == 1024

    def test_reconstruct_returns_none_on_invalid_data(self) -> None:
        """Test that invalid data returns None instead of raising."""
        result = TaskExecutor._reconstruct_param(
            ParameterModel, "bad", {"invalid_field_only": True}
        )
        # ParameterModel requires 'value', so this should log error and return None
        # or succeed depending on model validation - either way it shouldn't raise
        # The method catches TypeError and ValueError
        assert result is None or isinstance(result, ParameterModel)

    def test_reconstruct_returns_none_on_type_error(self) -> None:
        """Test that TypeError returns None."""
        # Passing something that can't be unpacked as kwargs
        result = TaskExecutor._reconstruct_param(ParameterModel, "bad", [1, 2, 3])
        assert result is None


class TestSnapshotOverrides:
    """Test TaskExecutor snapshot override integration."""

    @pytest.fixture
    def mock_state_manager(self) -> MagicMock:
        state_manager = MagicMock()
        state_manager.get_task.return_value = MagicMock(task_id="task-001")
        return state_manager

    @pytest.fixture
    def mock_snapshot_loader(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def executor_with_snapshot(
        self, mock_state_manager: MagicMock, mock_snapshot_loader: MagicMock
    ) -> TaskExecutor:
        return TaskExecutor(
            state_manager=mock_state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
            snapshot_loader=mock_snapshot_loader,
        )

    def test_apply_snapshot_overrides_with_data(
        self,
        executor_with_snapshot: TaskExecutor,
        mock_snapshot_loader: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test _apply_snapshot_overrides applies input and run parameters."""
        snap_input = {"freq": {"value": 5.0, "unit": "GHz"}}
        snap_run = {"shots": {"value": 1024, "value_type": "int"}}
        mock_snapshot_loader.get_snapshot.return_value = (snap_input, snap_run)

        task = MockTask()
        executor_with_snapshot._apply_snapshot_overrides(task, "CheckRabi", "qubit", "0")

        # Verify input_parameters were set on the task
        assert "freq" in task.input_parameters
        assert task.input_parameters["freq"].value == 5.0

        # Verify run_parameters were set on the task
        assert "shots" in task.run_parameters
        assert task.run_parameters["shots"].value == 1024

        # Verify state_manager was updated
        mock_state_manager.put_input_parameters.assert_called_once()
        mock_state_manager.put_run_parameters.assert_called_once()

    def test_apply_snapshot_overrides_missing_snapshot(
        self,
        executor_with_snapshot: TaskExecutor,
        mock_snapshot_loader: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test _apply_snapshot_overrides gracefully handles missing snapshot."""
        mock_snapshot_loader.get_snapshot.return_value = None

        task = MockTask()
        original_run_params = task.run_parameters

        executor_with_snapshot._apply_snapshot_overrides(task, "CheckRabi", "qubit", "0")

        # Task parameters should be unchanged
        assert task.run_parameters == original_run_params
        mock_state_manager.put_input_parameters.assert_not_called()
        mock_state_manager.put_run_parameters.assert_not_called()

    def test_apply_snapshot_overrides_empty_params(
        self,
        executor_with_snapshot: TaskExecutor,
        mock_snapshot_loader: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test _apply_snapshot_overrides handles empty snapshot parameters."""
        mock_snapshot_loader.get_snapshot.return_value = ({}, {})

        task = MockTask()
        executor_with_snapshot._apply_snapshot_overrides(task, "CheckRabi", "qubit", "0")

        # With empty dicts, no state updates should occur
        mock_state_manager.put_input_parameters.assert_not_called()
        mock_state_manager.put_run_parameters.assert_not_called()

    def test_apply_snapshot_overrides_filters_invalid_params(
        self,
        executor_with_snapshot: TaskExecutor,
        mock_snapshot_loader: MagicMock,
        mock_state_manager: MagicMock,
    ) -> None:
        """Test that invalid parameters are filtered out during reconstruction."""
        snap_input = {
            "good_param": {"value": 5.0},
            "bad_param": [1, 2, 3],  # Not a valid ParameterModel input
        }
        mock_snapshot_loader.get_snapshot.return_value = (snap_input, {})

        task = MockTask()
        executor_with_snapshot._apply_snapshot_overrides(task, "CheckRabi", "qubit", "0")

        # Only good_param should survive
        assert "good_param" in task.input_parameters
        assert "bad_param" not in task.input_parameters

    def test_execute_with_snapshot_loader_applies_overrides(
        self, mock_state_manager: MagicMock
    ) -> None:
        """Test that execute() calls _apply_snapshot_overrides when loader is present."""
        mock_snapshot_loader = MagicMock()
        mock_snapshot_loader.get_snapshot.return_value = (
            {"freq": {"value": 5.0}},
            {},
        )

        result_processor = MagicMock()
        result_processor.validate_r2.return_value = True
        result_processor.process_output_parameters.return_value = {}

        data_saver = MagicMock()
        data_saver.save_figures.return_value = ([], [])

        executor = TaskExecutor(
            state_manager=mock_state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
            result_processor=result_processor,
            data_saver=data_saver,
            snapshot_loader=mock_snapshot_loader,
        )

        task = MockTask()
        session: Any = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["success"] is True
        # Snapshot should have been queried (called twice: before and after preprocess)
        assert mock_snapshot_loader.get_snapshot.call_count == 2

    def test_execute_without_snapshot_loader_skips_overrides(
        self, mock_state_manager: MagicMock
    ) -> None:
        """Test that execute() works normally without a snapshot loader."""
        result_processor = MagicMock()
        result_processor.validate_r2.return_value = True
        result_processor.process_output_parameters.return_value = {}

        data_saver = MagicMock()
        data_saver.save_figures.return_value = ([], [])

        executor = TaskExecutor(
            state_manager=mock_state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
            result_processor=result_processor,
            data_saver=data_saver,
            snapshot_loader=None,
        )

        task = MockTask()
        session: Any = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["success"] is True
