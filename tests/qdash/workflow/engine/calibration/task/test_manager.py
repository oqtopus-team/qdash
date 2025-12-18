"""Smoke tests for TaskManager.

These tests verify the core behavior of TaskManager to serve as a safety net
during refactoring. Tests cover:
1. Task state management (start_task, end_task, update_task_status)
2. Parameter management (put_input_parameters, put_output_parameters)
3. Figure/raw data saving (save_figures, save_raw_data)
"""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import numpy as np
import plotly.graph_objs as go
import pytest
from qdash.datamodel.execution import ExecutionModel
from qdash.datamodel.task import (
    CalibDataModel,
    OutputParameterModel,
    QubitTaskModel,
    TaskResultModel,
    TaskStatusModel,
)
from qdash.workflow.engine.calibration.task.manager import TaskManager
from qdash.workflow.calibtasks.base import PostProcessResult, PreProcessResult, RunResult


class TestTaskStateManagement:
    """Test task state transitions."""

    def test_init_creates_empty_task_containers_for_qids(self):
        """Test TaskManager initialization with qids."""
        qids = ["0", "1", "2"]
        tm = TaskManager(username="test", execution_id="test-001", qids=qids, calib_dir="/tmp")

        for qid in qids:
            assert qid in tm.task_result.qubit_tasks
            assert qid in tm.task_result.coupling_tasks
            assert qid in tm.calib_data.qubit
            assert tm.task_result.qubit_tasks[qid] == []

    def test_init_handles_coupling_format(self):
        """Test TaskManager initialization with coupling qids."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        # Add coupling task container manually since "0-1" wasn't in initial qids
        tm.task_result.coupling_tasks["0-1"] = []
        tm.calib_data.coupling["0-1"] = {}

        assert "0-1" in tm.task_result.coupling_tasks
        assert "0-1" in tm.calib_data.coupling

    def test_ensure_task_exists_adds_new_task(self):
        """Test _ensure_task_exists adds task to container."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")

        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        tasks = tm.task_result.qubit_tasks["0"]
        assert len(tasks) == 1
        assert tasks[0].name == "CheckRabi"
        assert tasks[0].status == TaskStatusModel.SCHEDULED

    def test_ensure_task_exists_idempotent(self):
        """Test _ensure_task_exists is idempotent."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")

        tm._ensure_task_exists("CheckRabi", "qubit", "0")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        tasks = tm.task_result.qubit_tasks["0"]
        assert len(tasks) == 1

    def test_start_task_updates_status_to_running(self):
        """Test start_task changes status to RUNNING."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        tm.start_task("CheckRabi", "qubit", "0")

        task = tm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.RUNNING
        assert task.start_at != ""

    def test_end_task_sets_end_time(self):
        """Test end_task sets end_at and elapsed_time."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")
        tm.start_task("CheckRabi", "qubit", "0")

        tm.end_task("CheckRabi", "qubit", "0")

        task = tm.get_task("CheckRabi", "qubit", "0")
        assert task.end_at != ""
        assert task.elapsed_time != ""

    def test_update_task_status_to_completed(self):
        """Test update_task_status_to_completed."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        tm.update_task_status_to_completed("CheckRabi", "Task done", "qubit", "0")

        task = tm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.COMPLETED
        assert task.message == "Task done"

    def test_update_task_status_to_failed(self):
        """Test update_task_status_to_failed."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        tm.update_task_status_to_failed("CheckRabi", "Error occurred", "qubit", "0")

        task = tm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.FAILED
        assert task.message == "Error occurred"

    def test_update_task_status_to_skipped(self):
        """Test update_task_status_to_skipped."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        tm.update_task_status_to_skipped("CheckRabi", "Skipped", "qubit", "0")

        task = tm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.SKIPPED

    def test_get_task_raises_for_nonexistent_task(self):
        """Test get_task raises ValueError for unknown task."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")

        with pytest.raises(ValueError, match="Task 'Unknown' not found"):
            tm.get_task("Unknown", "qubit", "0")


class TestParameterManagement:
    """Test parameter handling."""

    def test_put_input_parameters(self):
        """Test put_input_parameters stores input params."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        input_params = {"frequency": 5.0, "amplitude": 0.1}
        tm.put_input_parameters("CheckRabi", input_params, "qubit", "0")

        task = tm.get_task("CheckRabi", "qubit", "0")
        assert task.input_parameters == input_params

    def test_put_output_parameters(self):
        """Test put_output_parameters stores output params and updates calib_data."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        output_param = OutputParameterModel(value=5.123, unit="GHz", description="Qubit frequency")
        output_params = {"qubit_frequency": output_param}
        tm.put_output_parameters("CheckRabi", output_params, "qubit", "0")

        task = tm.get_task("CheckRabi", "qubit", "0")
        assert "qubit_frequency" in task.output_parameters

        # Also updates calib_data
        assert "qubit_frequency" in tm.calib_data.qubit["0"]

    def test_get_output_parameter_by_task_name(self):
        """Test get_output_parameter_by_task_name retrieves output params."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        output_param = OutputParameterModel(value=5.123, unit="GHz")
        output_params = {"qubit_frequency": output_param}
        tm.put_output_parameters("CheckRabi", output_params, "qubit", "0")

        result = tm.get_output_parameter_by_task_name("CheckRabi", "qubit", "0")
        assert "qubit_frequency" in result

    def test_clear_qubit_calib_data(self):
        """Test _clear_qubit_calib_data removes specified parameters."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        output_param = OutputParameterModel(value=5.123, unit="GHz")
        output_params = {"qubit_frequency": output_param, "t1": OutputParameterModel(value=100)}
        tm.put_output_parameters("CheckRabi", output_params, "qubit", "0")

        tm._clear_qubit_calib_data("0", ["qubit_frequency"])

        assert "qubit_frequency" not in tm.calib_data.qubit["0"]
        assert "t1" in tm.calib_data.qubit["0"]


class TestFigureAndDataSaving:
    """Test figure and raw data saving."""

    def test_save_figures_creates_files(self):
        """Test save_figures creates png and json files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir=tmpdir)
            tm._ensure_task_exists("CheckRabi", "qubit", "0")

            # Create a simple plotly figure
            fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[4, 5, 6])])

            tm.save_figures([fig], "CheckRabi", "qubit", qid="0")

            task = tm.get_task("CheckRabi", "qubit", "0")

            # Check paths are recorded
            assert len(task.figure_path) == 1
            assert len(task.json_figure_path) == 1

            # Check files exist
            png_path = Path(task.figure_path[0])
            json_path = Path(task.json_figure_path[0])
            assert png_path.exists()
            assert json_path.exists()

    def test_save_raw_data_creates_csv_files(self):
        """Test save_raw_data creates CSV files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir=tmpdir)
            tm._ensure_task_exists("CheckRabi", "qubit", "0")

            # Create sample raw data
            raw_data = [np.array([1 + 2j, 3 + 4j, 5 + 6j])]

            tm.save_raw_data(raw_data, "CheckRabi", "qubit", "0")

            task = tm.get_task("CheckRabi", "qubit", "0")

            # Check paths are recorded
            assert len(task.raw_data_path) == 1

            # Check file exists
            csv_path = Path(task.raw_data_path[0])
            assert csv_path.exists()

            # Verify content
            loaded = np.loadtxt(csv_path, delimiter=",")
            assert loaded.shape == (3, 2)

    def test_resolve_conflict_increments_filename(self):
        """Test _resolve_conflict appends counter for existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir=tmpdir)

            # Create an existing file
            existing = Path(tmpdir) / "test.png"
            existing.touch()

            new_path = tm._resolve_conflict(existing)

            assert new_path != existing
            assert "test_1.png" in str(new_path)


class TestGlobalAndSystemTasks:
    """Test global and system task handling."""

    def test_global_task_lifecycle(self):
        """Test global task state management."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")

        tm._ensure_task_exists("GlobalInit", "global", "")

        assert len(tm.task_result.global_tasks) == 1
        assert tm.task_result.global_tasks[0].name == "GlobalInit"

        tm.start_task("GlobalInit", "global", "")
        task = tm.get_task("GlobalInit", "global", "")
        assert task.status == TaskStatusModel.RUNNING

    def test_system_task_lifecycle(self):
        """Test system task state management."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")

        tm._ensure_task_exists("SystemCheck", "system", "")

        assert len(tm.task_result.system_tasks) == 1
        assert tm.task_result.system_tasks[0].name == "SystemCheck"


class TestCouplingTasks:
    """Test coupling task handling."""

    def test_coupling_task_lifecycle(self):
        """Test coupling task state management."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        # Manually add coupling container
        tm.task_result.coupling_tasks["0-1"] = []
        tm.calib_data.coupling["0-1"] = {}

        tm._ensure_task_exists("CheckCoupling", "coupling", "0-1")

        tasks = tm.task_result.coupling_tasks["0-1"]
        assert len(tasks) == 1
        assert tasks[0].name == "CheckCoupling"

    def test_put_output_parameters_for_coupling(self):
        """Test put_output_parameters updates coupling calib_data."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm.task_result.coupling_tasks["0-1"] = []
        tm.calib_data.coupling["0-1"] = {}
        tm._ensure_task_exists("CheckCoupling", "coupling", "0-1")

        output_param = OutputParameterModel(value=0.05, unit="GHz")
        output_params = {"coupling_strength": output_param}
        tm.put_output_parameters("CheckCoupling", output_params, "coupling", "0-1")

        assert "coupling_strength" in tm.calib_data.coupling["0-1"]


class TestBatchOperations:
    """Test batch task operations."""

    def test_start_all_qid_tasks(self):
        """Test start_all_qid_tasks starts tasks for all qids."""
        qids = ["0", "1", "2"]
        tm = TaskManager(username="test", execution_id="test-001", qids=qids, calib_dir="/tmp")

        for qid in qids:
            tm._ensure_task_exists("CheckRabi", "qubit", qid)

        tm.start_all_qid_tasks("CheckRabi", "qubit", qids)

        for qid in qids:
            task = tm.get_task("CheckRabi", "qubit", qid)
            assert task.status == TaskStatusModel.RUNNING

    def test_update_not_executed_tasks_to_skipped(self):
        """Test update_not_executed_tasks_to_skipped marks pending tasks."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("Task1", "qubit", "0")
        tm._ensure_task_exists("Task2", "qubit", "0")

        # Complete one task, leave the other scheduled
        tm.update_task_status_to_completed("Task1", "Done", "qubit", "0")

        tm.update_not_executed_tasks_to_skipped("qubit", "0")

        task1 = tm.get_task("Task1", "qubit", "0")
        task2 = tm.get_task("Task2", "qubit", "0")

        assert task1.status == TaskStatusModel.COMPLETED  # Should remain completed
        assert task2.status == TaskStatusModel.SKIPPED


class TestControllerInfo:
    """Test controller info management."""

    def test_put_controller_info(self):
        """Test put_controller_info stores controller info."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")

        box_info = {"box1": {"type": "controller", "ip": "192.168.1.1"}}
        tm.put_controller_info(box_info)

        assert tm.controller_info == box_info


class TestCalibDataRetrieval:
    """Test calibration data retrieval."""

    def test_get_qubit_calib_data(self):
        """Test get_qubit_calib_data returns qubit calibration data."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        output_param = OutputParameterModel(value=5.123, unit="GHz")
        tm.put_output_parameters("CheckRabi", {"qubit_frequency": output_param}, "qubit", "0")

        data = tm.get_qubit_calib_data("0")
        assert "qubit_frequency" in data

    def test_get_coupling_calib_data(self):
        """Test get_coupling_calib_data returns coupling calibration data."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm.task_result.coupling_tasks["0-1"] = []
        tm.calib_data.coupling["0-1"] = {}
        tm._ensure_task_exists("CheckCoupling", "coupling", "0-1")

        output_param = OutputParameterModel(value=0.05, unit="GHz")
        tm.put_output_parameters(
            "CheckCoupling", {"coupling_strength": output_param}, "coupling", "0-1"
        )

        data = tm.get_coupling_calib_data("0-1")
        assert "coupling_strength" in data


class TestTaskTypeDetection:
    """Test task type detection methods."""

    def test_has_only_qubit_or_global_tasks(self):
        """Test has_only_qubit_or_global_tasks."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")
        tm._ensure_task_exists("GlobalInit", "global", "")

        assert tm.has_only_qubit_or_global_tasks(["CheckRabi", "GlobalInit"]) is True

    def test_this_task_is_completed(self):
        """Test this_task_is_completed."""
        tm = TaskManager(username="test", execution_id="test-001", qids=["0"], calib_dir="/tmp")
        tm._ensure_task_exists("CheckRabi", "qubit", "0")

        assert tm.this_task_is_completed("CheckRabi", "qubit", "0") is False

        tm.update_task_status_to_completed("CheckRabi", "Done", "qubit", "0")

        assert tm.this_task_is_completed("CheckRabi", "qubit", "0") is True


class TestExecuteTaskIntegration:
    """Integration tests for execute_task method.

    These tests require MongoDB connection (init_db fixture).
    """

    @pytest.fixture
    def mock_task(self):
        """Create a mock task for testing."""
        task = MagicMock()
        task.get_name.return_value = "CheckRabi"
        task.get_task_type.return_value = "qubit"
        task.is_qubit_task.return_value = True
        task.is_coupling_task.return_value = False
        task.backend = "fake"
        task.r2_threshold = 0.7
        task.name = "CheckRabi"
        return task

    @pytest.fixture
    def mock_backend(self):
        """Create a mock backend for testing."""
        backend = MagicMock()
        backend.name = "fake"
        return backend

    @pytest.fixture
    def mock_execution_manager(self):
        """Create a mock execution manager for testing."""
        from qdash.datamodel.execution import CalibDataModel, ExecutionStatusModel
        from qdash.datamodel.system_info import SystemInfoModel

        em = MagicMock()
        em.execution_id = "test-exec-001"
        em.chip_id = "test-chip"
        em.to_datamodel.return_value = ExecutionModel(
            username="test",
            name="test-execution",
            execution_id="test-exec-001",
            chip_id="test-chip",
            calib_data_path="/tmp/calib",
            tags=[],
            note={},
            status=ExecutionStatusModel.RUNNING,
            task_results={},
            controller_info={},
            fridge_info={},
            start_at="",
            end_at="",
            elapsed_time="",
            calib_data=CalibDataModel(qubit={}, coupling={}),
            message="",
            system_info=SystemInfoModel(),
        )
        em.update_with_task_manager.return_value = em
        return em

    @pytest.fixture
    def calib_dir(self):
        """Create a temporary calibration directory with required subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "task").mkdir()
            Path(tmpdir, "fig").mkdir()
            Path(tmpdir, "raw_data").mkdir()
            yield tmpdir

    def test_execute_task_without_run_result(
        self, init_db, mock_task, mock_backend, mock_execution_manager, calib_dir
    ):
        """Test execute_task when run returns None."""
        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        # Configure mock task to return None from run
        mock_task.preprocess.return_value = None
        mock_task.run.return_value = None

        # Patch ChipDocument and ChipHistoryDocument
        with (
            patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
            patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
        ):
            mock_chip_doc.get_current_chip.return_value = MagicMock()

            em_result, tm_result = tm.execute_task(
                task_instance=mock_task,
                backend=mock_backend,
                execution_manager=mock_execution_manager,
                qid="0",
            )

        # Verify task was completed
        task = tm_result.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.COMPLETED

    def test_execute_task_with_output_parameters(
        self, init_db, mock_task, mock_backend, mock_execution_manager, calib_dir
    ):
        """Test execute_task with output parameters."""
        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        # Configure mock task
        output_param = OutputParameterModel(value=5.123, unit="GHz")
        mock_task.preprocess.return_value = PreProcessResult(input_parameters={"freq": 5.0})
        mock_task.run.return_value = RunResult(raw_result={"data": [1, 2, 3]}, r2=None)
        mock_task.postprocess.return_value = PostProcessResult(
            output_parameters={"qubit_frequency": output_param},
            figures=[],
            raw_data=[],
        )
        mock_task.attach_task_id.return_value = {}

        with (
            patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
            patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
        ):
            mock_chip_doc.get_current_chip.return_value = MagicMock()

            em_result, tm_result = tm.execute_task(
                task_instance=mock_task,
                backend=mock_backend,
                execution_manager=mock_execution_manager,
                qid="0",
            )

        # Verify output parameters were stored
        task = tm_result.get_task("CheckRabi", "qubit", "0")
        assert "qubit_frequency" in task.output_parameters
        assert "qubit_frequency" in tm_result.calib_data.qubit["0"]

    def test_execute_task_with_r2_validation_pass(
        self, init_db, mock_task, mock_backend, mock_execution_manager, calib_dir
    ):
        """Test execute_task with passing R² validation."""
        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        output_param = OutputParameterModel(value=5.123, unit="GHz")
        mock_task.preprocess.return_value = None
        mock_task.run.return_value = RunResult(raw_result={}, r2={"0": 0.95})  # High R²
        mock_task.postprocess.return_value = PostProcessResult(
            output_parameters={"qubit_frequency": output_param},
            figures=[],
            raw_data=[],
        )
        mock_task.attach_task_id.return_value = {}
        mock_task.r2_threshold = 0.7

        with (
            patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
            patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
        ):
            mock_chip_doc.get_current_chip.return_value = MagicMock()

            em_result, tm_result = tm.execute_task(
                task_instance=mock_task,
                backend=mock_backend,
                execution_manager=mock_execution_manager,
                qid="0",
            )

        task = tm_result.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.COMPLETED
        # Output params should be retained for high R²
        assert "qubit_frequency" in tm_result.calib_data.qubit["0"]

    def test_execute_task_with_r2_validation_fail(
        self, init_db, mock_task, mock_backend, mock_execution_manager, calib_dir
    ):
        """Test execute_task with failing R² validation."""
        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        output_param = OutputParameterModel(value=5.123, unit="GHz")
        mock_task.preprocess.return_value = None
        mock_task.run.return_value = RunResult(raw_result={}, r2={"0": 0.3})  # Low R²
        mock_task.postprocess.return_value = PostProcessResult(
            output_parameters={"qubit_frequency": output_param},
            figures=[],
            raw_data=[],
        )
        mock_task.attach_task_id.return_value = {}
        mock_task.r2_threshold = 0.7

        with (
            patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
            patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
        ):
            mock_chip_doc.get_current_chip.return_value = MagicMock()

            with pytest.raises(ValueError, match="R² value too low"):
                tm.execute_task(
                    task_instance=mock_task,
                    backend=mock_backend,
                    execution_manager=mock_execution_manager,
                    qid="0",
                )

        # Task should be marked as failed
        task = tm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.FAILED

    def test_execute_task_with_fidelity_over_100_fails(
        self, init_db, mock_task, mock_backend, mock_execution_manager, calib_dir
    ):
        """Test execute_task fails when fidelity > 100% for RB tasks."""
        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        # Configure as randomized benchmarking task
        mock_task.get_name.return_value = "RandomizedBenchmarking"
        mock_task.name = "RandomizedBenchmarking"

        # Fidelity > 1.0 should fail
        output_param = OutputParameterModel(value=1.5, unit="")  # 150% fidelity
        mock_task.preprocess.return_value = None
        mock_task.run.return_value = RunResult(raw_result={}, r2=None)
        mock_task.postprocess.return_value = PostProcessResult(
            output_parameters={"fidelity": output_param},
            figures=[],
            raw_data=[],
        )
        mock_task.attach_task_id.return_value = {}

        with (
            patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
            patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
        ):
            mock_chip_doc.get_current_chip.return_value = MagicMock()

            with pytest.raises(ValueError, match="exceeds 100%"):
                tm.execute_task(
                    task_instance=mock_task,
                    backend=mock_backend,
                    execution_manager=mock_execution_manager,
                    qid="0",
                )

    def test_execute_task_with_figures(
        self, init_db, mock_task, mock_backend, mock_execution_manager, calib_dir
    ):
        """Test execute_task saves figures correctly."""
        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[4, 5, 6])])
        mock_task.preprocess.return_value = None
        mock_task.run.return_value = RunResult(raw_result={}, r2=None)
        mock_task.postprocess.return_value = PostProcessResult(
            output_parameters={},
            figures=[fig],
            raw_data=[],
        )

        with (
            patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
            patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
        ):
            mock_chip_doc.get_current_chip.return_value = MagicMock()

            em_result, tm_result = tm.execute_task(
                task_instance=mock_task,
                backend=mock_backend,
                execution_manager=mock_execution_manager,
                qid="0",
            )

        task = tm_result.get_task("CheckRabi", "qubit", "0")
        assert len(task.figure_path) == 1
        assert Path(task.figure_path[0]).exists()

    def test_execute_task_records_to_task_result_history(
        self, init_db, mock_task, mock_backend, mock_execution_manager, calib_dir
    ):
        """Test execute_task creates TaskResultHistoryDocument."""
        from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

        tm = TaskManager(
            username="test", execution_id="test-exec-001", qids=["0"], calib_dir=calib_dir
        )

        mock_task.preprocess.return_value = None
        mock_task.run.return_value = None

        with (
            patch("qdash.dbmodel.chip.ChipDocument") as mock_chip_doc,
            patch("qdash.dbmodel.chip_history.ChipHistoryDocument") as mock_chip_history,
        ):
            mock_chip_doc.get_current_chip.return_value = MagicMock()

            em_result, tm_result = tm.execute_task(
                task_instance=mock_task,
                backend=mock_backend,
                execution_manager=mock_execution_manager,
                qid="0",
            )

        # Verify TaskResultHistoryDocument was created
        task = tm_result.get_task("CheckRabi", "qubit", "0")
        doc = TaskResultHistoryDocument.find_one({"task_id": task.task_id}).run()
        assert doc is not None
        assert doc.name == "CheckRabi"
        assert doc.status == TaskStatusModel.COMPLETED
