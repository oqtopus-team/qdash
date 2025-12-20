"""Tests for ExecutionService."""

from collections.abc import Callable

import pytest
from qdash.datamodel.execution import (
    CalibDataModel,
    ExecutionModel,
    ExecutionStatusModel,
    TaskResultModel,
)
from qdash.datamodel.task import OutputParameterModel
from qdash.workflow.engine.execution.service import ExecutionService


class MockExecutionRepository:
    """Mock repository for testing."""

    def __init__(self):
        self.saved_models: list[ExecutionModel] = []
        self.stored_model: ExecutionModel | None = None

    def save(self, execution: ExecutionModel) -> None:
        self.saved_models.append(execution)
        self.stored_model = execution

    def find_by_id(self, execution_id: str) -> ExecutionModel | None:
        return self.stored_model

    def update_with_optimistic_lock(
        self,
        execution_id: str,
        update_func: Callable[[ExecutionModel], None],
        initial_model: ExecutionModel | None = None,
    ) -> ExecutionModel:
        if self.stored_model is None and initial_model:
            self.stored_model = initial_model

        if self.stored_model:
            update_func(self.stored_model)

        return self.stored_model


class TestExecutionServiceCreation:
    """Test ExecutionService creation."""

    def test_create_with_minimal_args(self):
        """Test creating service with minimal arguments."""
        mock_repo = MockExecutionRepository()

        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )

        assert service.execution_id == "exec-001"
        assert service.username == "test_user"
        assert service.chip_id == "chip_1"
        assert service.status == ExecutionStatusModel.SCHEDULED

    def test_create_with_all_args(self):
        """Test creating service with all arguments."""
        mock_repo = MockExecutionRepository()

        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            name="Test Execution",
            tags=["tag1", "tag2"],
            note={"key": "value"},
            repository=mock_repo,
        )

        assert service.state_manager.name == "Test Execution"
        assert service.state_manager.tags == ["tag1", "tag2"]
        # note is now an ExecutionNote model with extra data in .extra
        assert service.state_manager.note.extra == {"key": "value"}


class TestExecutionServiceLifecycle:
    """Test ExecutionService lifecycle methods."""

    def test_save_persists_to_repository(self):
        """Test save() persists to repository."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )

        result = service.save()

        assert result is service  # Returns self
        assert len(mock_repo.saved_models) == 1
        assert mock_repo.saved_models[0].execution_id == "exec-001"

    def test_start_updates_status_and_persists(self):
        """Test start() updates status and persists."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )

        result = service.start()

        assert result is service
        assert service.status == ExecutionStatusModel.RUNNING
        assert len(mock_repo.saved_models) == 1

    def test_complete_updates_status_and_persists(self):
        """Test complete() updates status and persists."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )
        service.start()

        result = service.complete()

        assert result is service
        assert service.status == ExecutionStatusModel.COMPLETED
        assert len(mock_repo.saved_models) == 2  # start + complete

    def test_fail_updates_status_and_persists(self):
        """Test fail() updates status and persists."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )
        service.start()

        result = service.fail()

        assert result is service
        assert service.status == ExecutionStatusModel.FAILED


class TestExecutionServiceMerge:
    """Test ExecutionService merge methods."""

    def test_merge_task_result(self):
        """Test merging task result."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )
        service.save()  # Initialize stored model

        task_result = TaskResultModel()
        result = service.merge_task_result("task-001", task_result)

        assert result is service
        assert "task-001" in service.task_results
        assert service.task_results["task-001"] == task_result

    def test_merge_calib_data(self):
        """Test merging calibration data."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )
        service.save()

        calib_data = CalibDataModel(
            qubit={"0": {"freq": OutputParameterModel(value=5.0)}},
            coupling={},
        )
        result = service.merge_calib_data(calib_data)

        assert result is service
        assert "0" in service.calib_data.qubit

    def test_merge_controller_info(self):
        """Test merging controller info."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )
        service.save()

        result = service.merge_controller_info({"box1": {"ip": "192.168.1.1"}})

        assert result is service
        assert "box1" in service.controller_info
        assert service.controller_info["box1"]["ip"] == "192.168.1.1"


class TestExecutionServiceReload:
    """Test ExecutionService reload."""

    def test_reload_updates_state_from_repository(self):
        """Test reload updates state from repository."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )
        service.save()

        # Modify stored model directly
        mock_repo.stored_model.status = ExecutionStatusModel.RUNNING

        result = service.reload()

        assert result is service
        assert service.status == ExecutionStatusModel.RUNNING

    def test_reload_raises_if_not_found(self):
        """Test reload raises if execution not found."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )
        # Don't save - stored_model will be None

        with pytest.raises(ValueError, match="not found"):
            service.reload()


class TestExecutionServiceFromExisting:
    """Test loading existing execution."""

    def test_from_existing_loads_model(self):
        """Test from_existing loads model from repository."""
        mock_repo = MockExecutionRepository()

        # Pre-populate repository
        mock_repo.stored_model = ExecutionModel(
            username="test_user",
            name="Test",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            note={},
            status=ExecutionStatusModel.RUNNING,
            task_results={},
            tags=[],
            controller_info={},
            fridge_info={},
            chip_id="chip_1",
            start_at="",
            end_at="",
            elapsed_time="",
            calib_data={"qubit": {}, "coupling": {}},
            message="",
            system_info={},
        )

        service = ExecutionService.from_existing("exec-001", repository=mock_repo)

        assert service is not None
        assert service.execution_id == "exec-001"
        assert service.status == ExecutionStatusModel.RUNNING

    def test_from_existing_returns_none_if_not_found(self):
        """Test from_existing returns None if not found."""
        mock_repo = MockExecutionRepository()

        service = ExecutionService.from_existing("nonexistent", repository=mock_repo)

        assert service is None


class TestExecutionServiceProperties:
    """Test ExecutionService property accessors."""

    def test_property_accessors(self):
        """Test all property accessors work correctly."""
        from qdash.workflow.engine.execution.models import ExecutionNote

        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )

        assert service.execution_id == "exec-001"
        assert service.username == "test_user"
        assert service.chip_id == "chip_1"
        assert service.calib_data_path == "/tmp/calib"
        assert service.status == ExecutionStatusModel.SCHEDULED
        assert isinstance(service.calib_data, CalibDataModel)
        assert isinstance(service.task_results, dict)
        assert isinstance(service.controller_info, dict)
        # note is now an ExecutionNote model
        assert isinstance(service.note, ExecutionNote)

    def test_note_setter(self):
        """Test note setter works."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )

        service.note = {"new_key": "new_value"}

        # Dict values are converted to ExecutionNote with data in .extra
        assert service.note.extra == {"new_key": "new_value"}

    def test_to_datamodel(self):
        """Test to_datamodel returns ExecutionModel."""
        mock_repo = MockExecutionRepository()
        service = ExecutionService.create(
            username="test_user",
            execution_id="exec-001",
            calib_data_path="/tmp/calib",
            chip_id="chip_1",
            repository=mock_repo,
        )

        model = service.to_datamodel()

        assert isinstance(model, ExecutionModel)
        assert model.execution_id == "exec-001"
