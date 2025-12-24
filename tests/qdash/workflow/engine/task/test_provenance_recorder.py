"""Tests for ProvenanceRecorder."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.datamodel.task import (
    CalibDataModel,
    OutputParameterModel,
    QubitTaskModel,
    TaskStatusModel,
)
from qdash.dbmodel.provenance import ProvenanceRelationType
from qdash.workflow.engine.task.provenance_recorder import ProvenanceRecorder


class TestProvenanceRecorder:
    """Test ProvenanceRecorder."""

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        param_version_repo = MagicMock()
        provenance_relation_repo = MagicMock()
        activity_repo = MagicMock()
        return {
            "param_version": param_version_repo,
            "provenance_relation": provenance_relation_repo,
            "activity": activity_repo,
        }

    @pytest.fixture
    def recorder(self, mock_repos):
        """Create a recorder with mock repositories."""
        return ProvenanceRecorder(
            parameter_version_repo=mock_repos["param_version"],
            provenance_relation_repo=mock_repos["provenance_relation"],
            activity_repo=mock_repos["activity"],
        )

    @pytest.fixture
    def sample_task(self):
        """Create a sample task with input and output parameters."""
        task = QubitTaskModel(
            name="CheckRabi",
            qid="Q0",
            status=TaskStatusModel.COMPLETED,
            input_parameters={
                "qubit_frequency": {"value": 5.0, "unit": "GHz"},
                "pi_amplitude": {"value": 0.5, "unit": "a.u."},
            },
            output_parameters={
                "rabi_frequency": OutputParameterModel(value=50.0, unit="MHz", error=0.5),
            },
        )
        task.start_at = datetime(2025, 1, 1, 10, 0, 0)
        task.end_at = datetime(2025, 1, 1, 10, 5, 0)
        return task

    @pytest.fixture
    def sample_execution_model(self):
        """Create a sample execution model."""
        return ExecutionModel(
            username="test-user",
            name="test-execution",
            execution_id="exec-001",
            chip_id="chip-001",
            project_id="project-001",
            calib_data_path="/tmp/calib",
            tags=[],
            note={},
            status=ExecutionStatusModel.RUNNING,
            task_results={},
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data=CalibDataModel(qubit={}, coupling={}),
            message="",
            system_info=SystemInfoModel(),
        )

    def test_record_from_task_creates_activity(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_from_task creates an activity record."""
        mock_repos["param_version"].get_current.return_value = None

        mock_entity = MagicMock()
        mock_entity.entity_id = "test-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_entity

        recorder.record_from_task(sample_task, sample_execution_model)

        mock_repos["activity"].create_activity.assert_called_once_with(
            execution_id="exec-001",
            task_id=sample_task.task_id,
            task_name="CheckRabi",
            project_id="project-001",
            task_type=sample_task.task_type,
            qid="Q0",
            chip_id="chip-001",
            started_at=sample_task.start_at,
            ended_at=sample_task.end_at,
            status=sample_task.status,
        )

    def test_record_from_task_records_used_relations_for_inputs(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_from_task records 'used' relations for input parameters."""
        mock_current_param = MagicMock()
        mock_current_param.entity_id = "existing-param-entity"
        mock_repos["param_version"].get_current.return_value = mock_current_param

        mock_entity = MagicMock()
        mock_entity.entity_id = "new-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_entity

        recorder.record_from_task(sample_task, sample_execution_model)

        # Should have called get_current for each input parameter
        assert mock_repos["param_version"].get_current.call_count == 2

        # Verify "used" relations were created for inputs
        used_calls = [
            c
            for c in mock_repos["provenance_relation"].create_relation.call_args_list
            if c.kwargs.get("relation_type") == ProvenanceRelationType.USED
        ]
        assert len(used_calls) == 2

    def test_record_from_task_creates_output_parameter_versions(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_from_task creates parameter versions for outputs."""
        mock_repos["param_version"].get_current.return_value = None

        mock_entity = MagicMock()
        mock_entity.entity_id = "output-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_entity

        recorder.record_from_task(sample_task, sample_execution_model)

        mock_repos["param_version"].create_version.assert_called_once_with(
            parameter_name="rabi_frequency",
            qid="Q0",
            value=50.0,
            execution_id="exec-001",
            task_id=sample_task.task_id,
            project_id="project-001",
            task_name="CheckRabi",
            chip_id="chip-001",
            unit="MHz",
            error=0.5,
            value_type="float",
        )

    def test_record_from_task_records_generated_by_relation(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_from_task records 'wasGeneratedBy' relation for outputs."""
        mock_repos["param_version"].get_current.return_value = None

        mock_entity = MagicMock()
        mock_entity.entity_id = "output-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_entity

        recorder.record_from_task(sample_task, sample_execution_model)

        generated_by_calls = [
            c
            for c in mock_repos["provenance_relation"].create_relation.call_args_list
            if c.kwargs.get("relation_type") == ProvenanceRelationType.GENERATED_BY
        ]
        assert len(generated_by_calls) == 1
        assert generated_by_calls[0].kwargs["source_id"] == "output-entity-id"
        assert generated_by_calls[0].kwargs["target_id"] == f"exec-001:{sample_task.task_id}"

    def test_record_from_task_records_derived_from_relations(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_from_task records 'wasDerivedFrom' relations."""
        mock_input_param = MagicMock()
        mock_input_param.entity_id = "input-entity-id"
        mock_repos["param_version"].get_current.return_value = mock_input_param

        mock_output_entity = MagicMock()
        mock_output_entity.entity_id = "output-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_output_entity

        recorder.record_from_task(sample_task, sample_execution_model)

        derived_from_calls = [
            c
            for c in mock_repos["provenance_relation"].create_relation.call_args_list
            if c.kwargs.get("relation_type") == ProvenanceRelationType.DERIVED_FROM
        ]
        # Should have 2 derived_from relations (one for each input parameter)
        assert len(derived_from_calls) == 2
        for call_obj in derived_from_calls:
            assert call_obj.kwargs["source_id"] == "output-entity-id"
            assert call_obj.kwargs["target_id"] == "input-entity-id"

    def test_record_from_task_handles_dict_output_parameters(
        self, recorder, mock_repos, sample_execution_model
    ):
        """Test record_from_task handles dict-style output parameters."""
        task = QubitTaskModel(
            name="CheckT1",
            qid="Q0",
            status=TaskStatusModel.COMPLETED,
            input_parameters={},
            output_parameters={
                "t1": {"value": 100.0, "unit": "us", "error": 5.0, "value_type": "float"},
            },
        )

        mock_repos["param_version"].get_current.return_value = None

        mock_entity = MagicMock()
        mock_entity.entity_id = "t1-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_entity

        recorder.record_from_task(task, sample_execution_model)

        mock_repos["param_version"].create_version.assert_called_once_with(
            parameter_name="t1",
            qid="Q0",
            value=100.0,
            execution_id="exec-001",
            task_id=task.task_id,
            project_id="project-001",
            task_name="CheckT1",
            chip_id="chip-001",
            unit="us",
            error=5.0,
            value_type="float",
        )

    def test_record_from_task_handles_raw_value_output_parameters(
        self, recorder, mock_repos, sample_execution_model
    ):
        """Test record_from_task handles raw value output parameters."""
        task = QubitTaskModel(
            name="CheckT2",
            qid="Q0",
            status=TaskStatusModel.COMPLETED,
            input_parameters={},
            output_parameters={"t2": 50.0},
        )

        mock_repos["param_version"].get_current.return_value = None

        mock_entity = MagicMock()
        mock_entity.entity_id = "t2-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_entity

        recorder.record_from_task(task, sample_execution_model)

        mock_repos["param_version"].create_version.assert_called_once_with(
            parameter_name="t2",
            qid="Q0",
            value=50.0,
            execution_id="exec-001",
            task_id=task.task_id,
            project_id="project-001",
            task_name="CheckT2",
            chip_id="chip-001",
            unit="",
            error=0.0,
            value_type="float",
        )

    def test_record_from_task_does_not_raise_on_error(
        self, recorder, mock_repos, sample_task, sample_execution_model
    ):
        """Test record_from_task logs error but does not raise."""
        mock_repos["activity"].create_activity.side_effect = Exception("DB Error")

        # Should not raise
        recorder.record_from_task(sample_task, sample_execution_model)

    def test_record_from_task_with_no_output_parameters(
        self, recorder, mock_repos, sample_execution_model
    ):
        """Test record_from_task with no output parameters."""
        task = QubitTaskModel(
            name="CheckQubit",
            qid="Q0",
            status=TaskStatusModel.COMPLETED,
            input_parameters={"qubit_frequency": {"value": 5.0}},
            output_parameters={},
        )

        mock_input_param = MagicMock()
        mock_input_param.entity_id = "input-entity-id"
        mock_repos["param_version"].get_current.return_value = mock_input_param

        recorder.record_from_task(task, sample_execution_model)

        # Activity should still be created
        mock_repos["activity"].create_activity.assert_called_once()
        # No output versions should be created
        mock_repos["param_version"].create_version.assert_not_called()
        # Only "used" relations should be created
        assert mock_repos["provenance_relation"].create_relation.call_count == 1

    def test_record_from_task_with_no_input_parameters(
        self, recorder, mock_repos, sample_execution_model
    ):
        """Test record_from_task with no input parameters."""
        task = QubitTaskModel(
            name="InitQubit",
            qid="Q0",
            status=TaskStatusModel.COMPLETED,
            input_parameters={},
            output_parameters={
                "initial_value": OutputParameterModel(value=0.0, unit="", error=0.0),
            },
        )

        mock_entity = MagicMock()
        mock_entity.entity_id = "init-entity-id"
        mock_repos["param_version"].create_version.return_value = mock_entity

        recorder.record_from_task(task, sample_execution_model)

        # Activity should be created
        mock_repos["activity"].create_activity.assert_called_once()
        # Output version should be created
        mock_repos["param_version"].create_version.assert_called_once()
        # Only "wasGeneratedBy" relation should be created (no "used" or "wasDerivedFrom")
        assert mock_repos["provenance_relation"].create_relation.call_count == 1
        call_obj = mock_repos["provenance_relation"].create_relation.call_args
        assert call_obj.kwargs["relation_type"] == ProvenanceRelationType.GENERATED_BY

    def test_default_repos_are_created(self):
        """Test that default repositories are created if not provided."""
        recorder = ProvenanceRecorder()

        assert recorder.parameter_version_repo is not None
        assert recorder.provenance_relation_repo is not None
        assert recorder.activity_repo is not None


class TestTaskHistoryRecorderWithProvenance:
    """Test TaskHistoryRecorder integration with ProvenanceRecorder."""

    @pytest.fixture
    def mock_task_repos(self):
        """Create mock repositories for TaskHistoryRecorder."""
        return {
            "task_result_history": MagicMock(),
            "chip": MagicMock(),
            "chip_history": MagicMock(),
        }

    @pytest.fixture
    def mock_provenance_recorder(self):
        """Create a mock ProvenanceRecorder."""
        return MagicMock()

    @pytest.fixture
    def sample_task(self):
        """Create a sample task."""
        return QubitTaskModel(
            name="CheckRabi",
            qid="Q0",
            status=TaskStatusModel.COMPLETED,
        )

    @pytest.fixture
    def sample_execution_model(self):
        """Create a sample execution model."""
        return ExecutionModel(
            username="test-user",
            name="test-execution",
            execution_id="exec-001",
            chip_id="chip-001",
            project_id="project-001",
            calib_data_path="/tmp/calib",
            tags=[],
            note={},
            status=ExecutionStatusModel.RUNNING,
            task_results={},
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data=CalibDataModel(qubit={}, coupling={}),
            message="",
            system_info=SystemInfoModel(),
        )

    def test_record_task_result_calls_provenance_when_enabled(
        self,
        mock_task_repos,
        mock_provenance_recorder,
        sample_task,
        sample_execution_model,
    ):
        """Test record_task_result calls provenance recorder when provided."""
        from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder

        recorder = TaskHistoryRecorder(
            task_result_history_repo=mock_task_repos["task_result_history"],
            chip_repo=mock_task_repos["chip"],
            chip_history_repo=mock_task_repos["chip_history"],
            provenance_recorder=mock_provenance_recorder,
        )

        recorder.record_task_result(sample_task, sample_execution_model)

        mock_provenance_recorder.record_from_task.assert_called_once_with(
            sample_task, sample_execution_model
        )

    def test_record_task_result_does_not_call_provenance_when_disabled(
        self,
        mock_task_repos,
        sample_task,
        sample_execution_model,
    ):
        """Test record_task_result does not call provenance when not provided."""
        from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder

        recorder = TaskHistoryRecorder(
            task_result_history_repo=mock_task_repos["task_result_history"],
            chip_repo=mock_task_repos["chip"],
            chip_history_repo=mock_task_repos["chip_history"],
            provenance_recorder=None,
        )

        recorder.record_task_result(sample_task, sample_execution_model)

        # Should not raise and task should still be saved
        mock_task_repos["task_result_history"].save.assert_called_once()

    def test_record_task_result_continues_on_provenance_error(
        self,
        mock_task_repos,
        mock_provenance_recorder,
        sample_task,
        sample_execution_model,
    ):
        """Test record_task_result continues even if provenance fails."""
        from qdash.workflow.engine.task.history_recorder import TaskHistoryRecorder

        mock_provenance_recorder.record_from_task.side_effect = Exception("Provenance Error")

        recorder = TaskHistoryRecorder(
            task_result_history_repo=mock_task_repos["task_result_history"],
            chip_repo=mock_task_repos["chip"],
            chip_history_repo=mock_task_repos["chip_history"],
            provenance_recorder=mock_provenance_recorder,
        )

        # Should not raise
        recorder.record_task_result(sample_task, sample_execution_model)

        # Task should still be saved
        mock_task_repos["task_result_history"].save.assert_called_once()
