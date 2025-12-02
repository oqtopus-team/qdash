"""Tests for TaskHistoryRecorder."""

from unittest.mock import MagicMock, patch

import pytest
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import (
    CalibDataModel,
    OutputParameterModel,
    QubitTaskModel,
    TaskStatusModel,
)
from qdash.workflow.engine.calibration.task_history_recorder import TaskHistoryRecorder


class TestTaskHistoryRecorder:
    """Test TaskHistoryRecorder."""

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        return {
            "task_result_history": MagicMock(),
            "chip": MagicMock(),
            "chip_history": MagicMock(),
        }

    @pytest.fixture
    def recorder(self, mock_repos):
        """Create a recorder with mock repositories."""
        return TaskHistoryRecorder(
            task_result_history_repo=mock_repos["task_result_history"],
            chip_repo=mock_repos["chip"],
            chip_history_repo=mock_repos["chip_history"],
        )

    @pytest.fixture
    def sample_task(self):
        """Create a sample task."""
        return QubitTaskModel(
            name="CheckRabi",
            qid="0",
            status=TaskStatusModel.COMPLETED,
        )

    @pytest.fixture
    def sample_execution_model(self):
        """Create a sample execution model."""
        return ExecutionModel(
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

    def test_record_task_result_calls_repo(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_task_result calls the repository."""
        recorder.record_task_result(sample_task, sample_execution_model)

        mock_repos["task_result_history"].save.assert_called_once_with(
            sample_task, sample_execution_model
        )

    def test_record_task_result_raises_on_error(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_task_result raises on error."""
        mock_repos["task_result_history"].save.side_effect = Exception("DB Error")

        with pytest.raises(Exception, match="DB Error"):
            recorder.record_task_result(sample_task, sample_execution_model)

    def test_update_chip_with_calib_data_calls_repo(self, recorder, mock_repos):
        """Test update_chip_with_calib_data calls the repository."""
        calib_data = CalibDataModel(
            qubit={"0": {"qubit_frequency": OutputParameterModel(value=5.0)}},
            coupling={},
        )

        recorder.update_chip_with_calib_data("test-chip", calib_data, "test-user")

        mock_repos["chip"].update_chip_data.assert_called_once_with(
            "test-chip", calib_data, "test-user"
        )

    def test_create_chip_history_snapshot_calls_repo(self, recorder, mock_repos):
        """Test create_chip_history_snapshot calls the repository."""
        recorder.create_chip_history_snapshot("test-user")

        mock_repos["chip_history"].create_history.assert_called_once_with("test-user")

    def test_record_completed_task_calls_all_repos(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_completed_task calls all repositories."""
        calib_data = CalibDataModel(qubit={"0": {}}, coupling={})

        recorder.record_completed_task(
            task=sample_task,
            execution_model=sample_execution_model,
            chip_id="test-chip",
            calib_data=calib_data,
            username="test-user",
            create_history=True,
        )

        mock_repos["task_result_history"].save.assert_called_once()
        mock_repos["chip"].update_chip_data.assert_called_once()
        mock_repos["chip_history"].create_history.assert_called_once()

    def test_record_completed_task_skips_history_when_disabled(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_completed_task skips history when create_history=False."""
        calib_data = CalibDataModel(qubit={"0": {}}, coupling={})

        recorder.record_completed_task(
            task=sample_task,
            execution_model=sample_execution_model,
            chip_id="test-chip",
            calib_data=calib_data,
            username="test-user",
            create_history=False,
        )

        mock_repos["task_result_history"].save.assert_called_once()
        mock_repos["chip"].update_chip_data.assert_called_once()
        mock_repos["chip_history"].create_history.assert_not_called()

    def test_default_repos_are_created(self):
        """Test that default repositories are created if not provided."""
        recorder = TaskHistoryRecorder()

        # Should not raise
        assert recorder.task_result_history_repo is not None
        assert recorder.chip_repo is not None
        assert recorder.chip_history_repo is not None
