"""Tests for TaskStateManager."""

import pytest
from qdash.datamodel.task import OutputParameterModel, TaskStatusModel
from qdash.workflow.engine.calibration.task_state_manager import TaskStateManager


class TestTaskStateManagerInit:
    """Test TaskStateManager initialization."""

    def test_init_creates_containers_for_qids(self):
        """Test initialization creates containers for given qids."""
        qids = ["0", "1", "2"]
        tsm = TaskStateManager(qids=qids)

        for qid in qids:
            assert qid in tsm.task_result.qubit_tasks
            assert qid in tsm.task_result.coupling_tasks
            assert qid in tsm.calib_data.qubit
            assert tsm.task_result.qubit_tasks[qid] == []

    def test_init_without_qids(self):
        """Test initialization without qids creates empty containers."""
        tsm = TaskStateManager()

        assert tsm.task_result.qubit_tasks == {}
        assert tsm.task_result.global_tasks == []


class TestTaskCreation:
    """Test task creation and lookup."""

    def test_ensure_task_exists_creates_qubit_task(self):
        """Test _ensure_task_exists creates a qubit task."""
        tsm = TaskStateManager(qids=["0"])

        task = tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        assert task.name == "CheckRabi"
        assert task.status == TaskStatusModel.SCHEDULED
        assert len(tsm.task_result.qubit_tasks["0"]) == 1

    def test_ensure_task_exists_is_idempotent(self):
        """Test _ensure_task_exists returns existing task."""
        tsm = TaskStateManager(qids=["0"])

        task1 = tsm._ensure_task_exists("CheckRabi", "qubit", "0")
        task2 = tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        assert task1 is task2
        assert len(tsm.task_result.qubit_tasks["0"]) == 1

    def test_ensure_task_exists_creates_global_task(self):
        """Test _ensure_task_exists creates a global task."""
        tsm = TaskStateManager()

        task = tsm._ensure_task_exists("GlobalInit", "global", "")

        assert task.name == "GlobalInit"
        assert len(tsm.task_result.global_tasks) == 1

    def test_ensure_task_exists_creates_system_task(self):
        """Test _ensure_task_exists creates a system task."""
        tsm = TaskStateManager()

        task = tsm._ensure_task_exists("SystemCheck", "system", "")

        assert task.name == "SystemCheck"
        assert len(tsm.task_result.system_tasks) == 1

    def test_get_task_returns_task(self):
        """Test get_task returns the task."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")

        assert task.name == "CheckRabi"

    def test_get_task_raises_for_nonexistent(self):
        """Test get_task raises ValueError for nonexistent task."""
        tsm = TaskStateManager(qids=["0"])

        with pytest.raises(ValueError, match="not found"):
            tsm.get_task("Unknown", "qubit", "0")


class TestTaskStatusTransitions:
    """Test task status transitions."""

    def test_start_task_sets_running(self):
        """Test start_task sets status to RUNNING."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        tsm.start_task("CheckRabi", "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.RUNNING
        assert task.start_at != ""

    def test_end_task_sets_end_time(self):
        """Test end_task sets end_at and elapsed_time."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")
        tsm.start_task("CheckRabi", "qubit", "0")

        tsm.end_task("CheckRabi", "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.end_at != ""
        assert task.elapsed_time != ""

    def test_update_status_to_completed(self):
        """Test update_task_status_to_completed."""
        tsm = TaskStateManager(qids=["0"])

        tsm.update_task_status_to_completed("CheckRabi", "Done", "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.COMPLETED
        assert task.message == "Done"

    def test_update_status_to_failed(self):
        """Test update_task_status_to_failed."""
        tsm = TaskStateManager(qids=["0"])

        tsm.update_task_status_to_failed("CheckRabi", "Error", "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.FAILED
        assert task.message == "Error"

    def test_update_status_to_skipped(self):
        """Test update_task_status_to_skipped."""
        tsm = TaskStateManager(qids=["0"])

        tsm.update_task_status_to_skipped("CheckRabi", "Skipped", "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.status == TaskStatusModel.SKIPPED


class TestParameterManagement:
    """Test parameter management."""

    def test_put_input_parameters(self):
        """Test put_input_parameters stores input params."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        tsm.put_input_parameters("CheckRabi", {"freq": 5.0}, "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.input_parameters == {"freq": 5.0}

    def test_put_output_parameters_updates_task_and_calib_data(self):
        """Test put_output_parameters updates task and calibration data."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        output_param = OutputParameterModel(value=5.123, unit="GHz")
        tsm.put_output_parameters("CheckRabi", {"qubit_frequency": output_param}, "qubit", "0")

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert "qubit_frequency" in task.output_parameters
        assert "qubit_frequency" in tsm.calib_data.qubit["0"]

    def test_put_output_parameters_for_coupling(self):
        """Test put_output_parameters for coupling task."""
        tsm = TaskStateManager()
        tsm.task_result.coupling_tasks["0-1"] = []
        tsm.calib_data.coupling["0-1"] = {}

        output_param = OutputParameterModel(value=0.05, unit="GHz")
        tsm.put_output_parameters("CheckCoupling", {"coupling_strength": output_param}, "coupling", "0-1")

        assert "coupling_strength" in tsm.calib_data.coupling["0-1"]

    def test_get_output_parameter_by_task_name(self):
        """Test get_output_parameter_by_task_name."""
        tsm = TaskStateManager(qids=["0"])
        output_param = OutputParameterModel(value=5.0)
        tsm.put_output_parameters("CheckRabi", {"freq": output_param}, "qubit", "0")

        result = tsm.get_output_parameter_by_task_name("CheckRabi", "qubit", "0")

        assert "freq" in result

    def test_clear_qubit_calib_data(self):
        """Test _clear_qubit_calib_data removes parameters."""
        tsm = TaskStateManager(qids=["0"])
        tsm.calib_data.qubit["0"] = {
            "qubit_frequency": OutputParameterModel(value=5.0),
            "t1": OutputParameterModel(value=100.0),
        }

        tsm._clear_qubit_calib_data("0", ["qubit_frequency"])

        assert "qubit_frequency" not in tsm.calib_data.qubit["0"]
        assert "t1" in tsm.calib_data.qubit["0"]


class TestBatchOperations:
    """Test batch operations."""

    def test_start_all_qid_tasks(self):
        """Test start_all_qid_tasks starts tasks for all qids."""
        qids = ["0", "1", "2"]
        tsm = TaskStateManager(qids=qids)
        for qid in qids:
            tsm._ensure_task_exists("CheckRabi", "qubit", qid)

        tsm.start_all_qid_tasks("CheckRabi", "qubit", qids)

        for qid in qids:
            task = tsm.get_task("CheckRabi", "qubit", qid)
            assert task.status == TaskStatusModel.RUNNING

    def test_update_not_executed_tasks_to_skipped(self):
        """Test update_not_executed_tasks_to_skipped marks scheduled tasks."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("Task1", "qubit", "0")
        tsm._ensure_task_exists("Task2", "qubit", "0")
        tsm.update_task_status_to_completed("Task1", "Done", "qubit", "0")

        tsm.update_not_executed_tasks_to_skipped("qubit", "0")

        task1 = tsm.get_task("Task1", "qubit", "0")
        task2 = tsm.get_task("Task2", "qubit", "0")
        assert task1.status == TaskStatusModel.COMPLETED
        assert task2.status == TaskStatusModel.SKIPPED


class TestCalibDataRetrieval:
    """Test calibration data retrieval."""

    def test_get_qubit_calib_data(self):
        """Test get_qubit_calib_data."""
        tsm = TaskStateManager(qids=["0"])
        tsm.calib_data.qubit["0"]["freq"] = OutputParameterModel(value=5.0)

        data = tsm.get_qubit_calib_data("0")

        assert "freq" in data

    def test_get_coupling_calib_data(self):
        """Test get_coupling_calib_data."""
        tsm = TaskStateManager()
        tsm.calib_data.coupling["0-1"] = {"coupling": OutputParameterModel(value=0.05)}

        data = tsm.get_coupling_calib_data("0-1")

        assert "coupling" in data

    def test_get_calib_data_returns_empty_for_unknown(self):
        """Test get_calib_data returns empty dict for unknown qid."""
        tsm = TaskStateManager()

        assert tsm.get_qubit_calib_data("unknown") == {}
        assert tsm.get_coupling_calib_data("unknown") == {}


class TestFigureAndDataPaths:
    """Test figure and data path management."""

    def test_set_figure_paths(self):
        """Test set_figure_paths."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        tsm.set_figure_paths("CheckRabi", "qubit", "0", ["/path/to/fig.png"], ["/path/to/fig.json"])

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.figure_path == ["/path/to/fig.png"]
        assert task.json_figure_path == ["/path/to/fig.json"]

    def test_set_raw_data_paths(self):
        """Test set_raw_data_paths."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        tsm.set_raw_data_paths("CheckRabi", "qubit", "0", ["/path/to/raw.csv"])

        task = tsm.get_task("CheckRabi", "qubit", "0")
        assert task.raw_data_path == ["/path/to/raw.csv"]


class TestTaskChecks:
    """Test task check methods."""

    def test_this_task_is_completed_returns_true(self):
        """Test this_task_is_completed returns True for completed task."""
        tsm = TaskStateManager(qids=["0"])
        tsm.update_task_status_to_completed("CheckRabi", "Done", "qubit", "0")

        assert tsm.this_task_is_completed("CheckRabi", "qubit", "0") is True

    def test_this_task_is_completed_returns_false(self):
        """Test this_task_is_completed returns False for non-completed task."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("CheckRabi", "qubit", "0")

        assert tsm.this_task_is_completed("CheckRabi", "qubit", "0") is False

    def test_this_task_is_completed_returns_false_for_nonexistent(self):
        """Test this_task_is_completed returns False for nonexistent task."""
        tsm = TaskStateManager(qids=["0"])

        assert tsm.this_task_is_completed("Unknown", "qubit", "0") is False

    def test_has_only_qubit_or_global_tasks(self):
        """Test has_only_qubit_or_global_tasks."""
        tsm = TaskStateManager(qids=["0"])
        tsm._ensure_task_exists("QubitTask", "qubit", "0")
        tsm._ensure_task_exists("GlobalTask", "global", "")

        assert tsm.has_only_qubit_or_global_tasks(["QubitTask", "GlobalTask"]) is True
