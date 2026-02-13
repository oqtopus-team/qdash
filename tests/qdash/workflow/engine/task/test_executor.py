"""Tests for TaskExecutor."""

from unittest.mock import MagicMock

import pytest
from qdash.datamodel.task import ParameterModel, QubitTaskModel, RunParameterModel, TaskStatusModel
from qdash.workflow.calibtasks.base import PostProcessResult, PreProcessResult, RunResult
from qdash.workflow.engine.task.executor import (
    TaskExecutionError,
    TaskExecutor,
    TaskProtocol,
)
from qdash.workflow.engine.task.result_processor import (
    FidelityValidationError,
    R2ValidationError,
)


class MockTask:
    """Mock task for testing."""

    def __init__(
        self,
        name: str = "CheckRabi",
        task_type: str = "qubit",
        r2_threshold: float = 0.7,
        backend: str = "fake",
    ):
        self.name = name
        self._task_type = task_type
        self.r2_threshold = r2_threshold
        self.backend = backend
        self.run_parameters = {}

    def get_name(self) -> str:
        return self.name

    def get_task_type(self) -> str:
        return self._task_type

    def is_qubit_task(self) -> bool:
        return self._task_type == "qubit"

    def is_coupling_task(self) -> bool:
        return self._task_type == "coupling"

    def preprocess(self, session, qid):
        return PreProcessResult(input_parameters={"param1": ParameterModel(value=1.0)})

    def run(self, session, qid):
        return RunResult(raw_result={"data": [1, 2, 3]}, r2={"0": 0.95})

    def postprocess(self, session, execution_id, run_result, qid):
        return PostProcessResult(
            output_parameters={"qubit_frequency": ParameterModel(value=5.0)},
            figures=[],
            raw_data=[],
        )

    def attach_task_id(self, task_id):
        return {}


class MockSession:
    """Mock session for testing."""

    name = "test-session"


class TestTaskExecutorInit:
    """Test TaskExecutor initialization."""

    def test_init_with_all_dependencies(self):
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

    def test_init_creates_default_dependencies(self):
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
    def mock_state_manager(self):
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
    def mock_result_processor(self):
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
    def mock_data_saver(self):
        """Create a mock data saver."""
        saver = MagicMock()
        saver.save_figures.return_value = ([], [])
        saver.save_raw_data.return_value = []
        return saver

    @pytest.fixture
    def executor(self, mock_state_manager, mock_result_processor, mock_data_saver):
        """Create an executor with mocked dependencies."""
        return TaskExecutor(
            state_manager=mock_state_manager,
            calib_dir="/tmp/calib",
            execution_id="exec-001",
            task_manager_id="tm-001",
            result_processor=mock_result_processor,
            data_saver=mock_data_saver,
        )

    def test_execute_task_success(self, executor, mock_state_manager):
        """Test successful task execution."""
        task = MockTask()
        session = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["success"] is True
        assert result["task_name"] == "CheckRabi"
        assert result["qid"] == "0"
        mock_state_manager.start_task.assert_called_once_with("CheckRabi", "qubit", "0")
        mock_state_manager.end_task.assert_called_once_with("CheckRabi", "qubit", "0")

    def test_execute_task_calls_preprocess(self, executor, mock_state_manager):
        """Test execute_task calls preprocess and stores input parameters."""
        task = MockTask()
        session = MockSession()

        executor.execute_task(task, session, "0")

        mock_state_manager.put_input_parameters.assert_called_once()
        call_args = mock_state_manager.put_input_parameters.call_args
        assert call_args[0][0] == "CheckRabi"
        assert "param1" in call_args[0][1]
        assert call_args[0][1]["param1"].value == 1.0

    def test_execute_task_handles_no_run_result(self, executor, mock_state_manager):
        """Test execute_task handles task with no run result."""
        task = MockTask()
        task.run = MagicMock(return_value=None)
        session = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["success"] is True
        assert result["message"] == "Completed without run result"
        mock_state_manager.update_task_status_to_completed.assert_called_once()

    def test_execute_task_validates_r2(self, executor, mock_result_processor):
        """Test execute_task validates R² values."""
        task = MockTask()
        session = MockSession()

        executor.execute_task(task, session, "0")

        mock_result_processor.validate_r2.assert_called_once()
        call_args = mock_result_processor.validate_r2.call_args
        assert call_args[0][0] == {"0": 0.95}  # r2 dict
        assert call_args[0][1] == "0"  # qid
        assert call_args[0][2] == 0.7  # threshold from task

    def test_execute_task_raises_on_r2_validation_failure(
        self, executor, mock_result_processor, mock_state_manager
    ):
        """Test execute_task raises on R² validation failure."""
        mock_result_processor.validate_r2.side_effect = R2ValidationError("R² value too low")
        task = MockTask()
        session = MockSession()

        with pytest.raises(ValueError, match="R² value too low"):
            executor.execute_task(task, session, "0")

        mock_state_manager.update_task_status_to_failed.assert_called_once()

    def test_execute_task_raises_on_fidelity_validation_failure(
        self, executor, mock_result_processor, mock_state_manager
    ):
        """Test execute_task raises on fidelity validation failure."""
        mock_result_processor.process_output_parameters.side_effect = FidelityValidationError(
            "Fidelity exceeds 100%"
        )
        task = MockTask()
        session = MockSession()

        with pytest.raises(ValueError, match="Fidelity exceeds 100%"):
            executor.execute_task(task, session, "0")

        mock_state_manager.update_task_status_to_failed.assert_called_once()

    def test_execute_task_raises_task_execution_error_on_exception(
        self, executor, mock_state_manager
    ):
        """Test execute_task raises TaskExecutionError on unexpected exception."""
        task = MockTask()
        task.run = MagicMock(side_effect=RuntimeError("Unexpected error"))
        session = MockSession()

        with pytest.raises(TaskExecutionError, match="Task CheckRabi failed"):
            executor.execute_task(task, session, "0")

        mock_state_manager.update_task_status_to_failed.assert_called_once()

    def test_execute_task_always_calls_end_task(self, executor, mock_state_manager):
        """Test execute_task always calls end_task even on failure."""
        task = MockTask()
        task.run = MagicMock(side_effect=RuntimeError("Error"))
        session = MockSession()

        with pytest.raises(TaskExecutionError):
            executor.execute_task(task, session, "0")

        # end_task should always be called (in finally block)
        mock_state_manager.end_task.assert_called_once()

    def test_execute_task_saves_figures(self, executor, mock_data_saver):
        """Test execute_task saves figures from postprocess result."""
        import plotly.graph_objects as go

        task = MockTask()
        fig = go.Figure()
        task.postprocess = MagicMock(
            return_value=PostProcessResult(
                output_parameters={},
                figures=[fig],
                raw_data=[],
            )
        )
        session = MockSession()

        executor.execute_task(task, session, "0")

        mock_data_saver.save_figures.assert_called_once()

    def test_execute_task_saves_raw_data(self, executor, mock_data_saver):
        """Test execute_task saves raw data from postprocess result."""
        task = MockTask()
        task.postprocess = MagicMock(
            return_value=PostProcessResult(
                output_parameters={},
                figures=[],
                raw_data=[{"x": [1, 2], "y": [3, 4]}],
            )
        )
        session = MockSession()

        executor.execute_task(task, session, "0")

        mock_data_saver.save_raw_data.assert_called_once()

    def test_execute_task_processes_output_parameters(
        self, executor, mock_result_processor, mock_state_manager
    ):
        """Test execute_task processes and stores output parameters."""
        task = MockTask()
        session = MockSession()

        result = executor.execute_task(task, session, "0")

        mock_result_processor.process_output_parameters.assert_called_once()
        mock_state_manager.put_output_parameters.assert_called_once()
        assert "output_parameters" in result

    def test_execute_task_returns_r2_in_result(self, executor):
        """Test execute_task returns R² value in result."""
        task = MockTask()
        session = MockSession()

        result = executor.execute_task(task, session, "0")

        assert result["r2"] == {"0": 0.95}

    def test_execute_task_records_run_parameters(self, executor, mock_state_manager):
        """Test execute_task records run_parameters when present."""
        task = MockTask()
        task.run_parameters = {
            "shots": RunParameterModel(value=1024, value_type="int", description="Number of shots"),
            "interval": RunParameterModel(value=150, value_type="int", unit="us"),
        }
        session = MockSession()

        executor.execute_task(task, session, "0")

        mock_state_manager.put_run_parameters.assert_called_once()
        call_args = mock_state_manager.put_run_parameters.call_args[0]
        assert call_args[0] == "CheckRabi"  # task_name
        assert "shots" in call_args[1]  # run_params dict
        assert "interval" in call_args[1]
        assert call_args[1]["shots"]["value"] == 1024
        assert call_args[2] == "qubit"  # task_type
        assert call_args[3] == "0"  # qid

    def test_execute_task_skips_empty_run_parameters(self, executor, mock_state_manager):
        """Test execute_task does not call put_run_parameters when empty."""
        task = MockTask()
        task.run_parameters = {}
        session = MockSession()

        executor.execute_task(task, session, "0")

        mock_state_manager.put_run_parameters.assert_not_called()


class TestTaskExecutorHelperMethods:
    """Test TaskExecutor helper methods."""

    @pytest.fixture
    def executor(self):
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

    def test_run_preprocess_returns_result(self, executor):
        """Test _run_preprocess returns preprocess result."""
        task = MockTask()
        session = MockSession()

        result = executor._run_preprocess(task, session, "0")

        assert result is not None
        assert "param1" in result.input_parameters
        assert result.input_parameters["param1"].value == 1.0

    def test_run_preprocess_handles_exception(self, executor):
        """Test _run_preprocess handles exception gracefully."""
        task = MockTask()
        task.preprocess = MagicMock(side_effect=RuntimeError("Preprocess failed"))
        session = MockSession()

        result = executor._run_preprocess(task, session, "0")

        assert result is None

    def test_run_task_returns_result(self, executor):
        """Test _run_task returns run result."""
        task = MockTask()
        session = MockSession()

        result = executor._run_task(task, session, "0")

        assert result is not None
        assert result.raw_result == {"data": [1, 2, 3]}
        assert result.r2 == {"0": 0.95}

    def test_run_postprocess_returns_result(self, executor):
        """Test _run_postprocess returns postprocess result."""
        task = MockTask()
        session = MockSession()
        run_result = RunResult(raw_result={}, r2={})

        result = executor._run_postprocess(task, session, run_result, "0")

        assert result is not None
        assert "qubit_frequency" in result.output_parameters


class TestTaskProtocol:
    """Test TaskProtocol compliance."""

    def test_mock_task_satisfies_protocol(self):
        """Test that MockTask satisfies TaskProtocol."""
        task = MockTask()

        assert isinstance(task, TaskProtocol)

    def test_protocol_requires_name_attribute(self):
        """Test TaskProtocol requires name attribute."""

        class IncompleteTask:
            def get_name(self):
                return "test"

        task = IncompleteTask()
        assert not isinstance(task, TaskProtocol)


class TestCouplingTask:
    """Test TaskExecutor with coupling tasks."""

    @pytest.fixture
    def executor(self):
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

    def test_execute_coupling_task(self, executor):
        """Test executing a coupling task."""
        task = MockTask(name="CheckCoupling", task_type="coupling")
        session = MockSession()

        result = executor.execute_task(task, session, "0-1")

        assert result["task_type"] == "coupling"
        assert result["qid"] == "0-1"
        assert result["success"] is True
