"""Tests for InMemory repository implementations."""

import pytest
from qdash.datamodel.execution import (
    ExecutionModel,
    ExecutionStatusModel,
)
from qdash.repository.inmemory import (
    InMemoryExecutionCounterRepository,
    InMemoryExecutionLockRepository,
    InMemoryExecutionRepository,
    InMemoryTaskRepository,
    InMemoryUserRepository,
)


class TestInMemoryExecutionRepository:
    """Test InMemoryExecutionRepository."""

    def test_save_and_find_by_id(self):
        """Test saving and finding execution."""
        repo = InMemoryExecutionRepository()
        model = ExecutionModel(
            username="test_user",
            name="Test",
            execution_id="exec-001",
            calib_data_path="/tmp",
            note={},
            status=ExecutionStatusModel.SCHEDULED,
            task_results={},
            tags=[],
            chip_id="chip_1",
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data={"qubit": {}, "coupling": {}},
            message="",
            system_info={},
        )

        repo.save(model)
        found = repo.find_by_id("exec-001")

        assert found is not None
        assert found.execution_id == "exec-001"
        assert found.username == "test_user"

    def test_find_by_id_not_found(self):
        """Test finding non-existent execution."""
        repo = InMemoryExecutionRepository()
        found = repo.find_by_id("nonexistent")
        assert found is None

    def test_update_with_optimistic_lock(self):
        """Test updating execution with optimistic lock."""
        repo = InMemoryExecutionRepository()
        model = ExecutionModel(
            username="test_user",
            name="Test",
            execution_id="exec-001",
            calib_data_path="/tmp",
            note={},
            status=ExecutionStatusModel.SCHEDULED,
            task_results={},
            tags=[],
            chip_id="chip_1",
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data={"qubit": {}, "coupling": {}},
            message="",
            system_info={},
        )
        repo.save(model)

        def update_status(m: ExecutionModel) -> None:
            m.status = ExecutionStatusModel.RUNNING

        updated = repo.update_with_optimistic_lock("exec-001", update_status)

        assert updated.status == ExecutionStatusModel.RUNNING

    def test_update_with_initial_model(self):
        """Test updating with initial model when not found."""
        repo = InMemoryExecutionRepository()
        initial = ExecutionModel(
            username="test_user",
            name="Test",
            execution_id="exec-001",
            calib_data_path="/tmp",
            note={},
            status=ExecutionStatusModel.SCHEDULED,
            task_results={},
            tags=[],
            chip_id="chip_1",
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data={"qubit": {}, "coupling": {}},
            message="",
            system_info={},
        )

        def update_status(m: ExecutionModel) -> None:
            m.status = ExecutionStatusModel.RUNNING

        updated = repo.update_with_optimistic_lock("exec-001", update_status, initial_model=initial)

        assert updated.status == ExecutionStatusModel.RUNNING

    def test_update_raises_when_not_found(self):
        """Test update raises error when not found and no initial model."""
        repo = InMemoryExecutionRepository()

        def update_status(m: ExecutionModel) -> None:
            m.status = ExecutionStatusModel.RUNNING

        with pytest.raises(ValueError, match="not found"):
            repo.update_with_optimistic_lock("nonexistent", update_status)

    def test_clear(self):
        """Test clearing repository."""
        repo = InMemoryExecutionRepository()
        model = ExecutionModel(
            username="test_user",
            name="Test",
            execution_id="exec-001",
            calib_data_path="/tmp",
            note={},
            status=ExecutionStatusModel.SCHEDULED,
            task_results={},
            tags=[],
            chip_id="chip_1",
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data={"qubit": {}, "coupling": {}},
            message="",
            system_info={},
        )
        repo.save(model)

        repo.clear()

        assert repo.find_by_id("exec-001") is None


class TestInMemoryExecutionCounterRepository:
    """Test InMemoryExecutionCounterRepository."""

    def test_get_next_index_starts_at_zero(self):
        """Test counter starts at 0."""
        repo = InMemoryExecutionCounterRepository()
        index = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        assert index == 0

    def test_get_next_index_increments(self):
        """Test counter increments."""
        repo = InMemoryExecutionCounterRepository()
        index1 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        index2 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        index3 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")

        assert index1 == 0
        assert index2 == 1
        assert index3 == 2

    def test_different_keys_have_separate_counters(self):
        """Test different key combinations have separate counters."""
        repo = InMemoryExecutionCounterRepository()

        # Different dates
        index1 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        index2 = repo.get_next_index("20240102", "alice", "chip_1", "proj-1")

        assert index1 == 0
        assert index2 == 0

        # Different users
        index3 = repo.get_next_index("20240101", "bob", "chip_1", "proj-1")
        assert index3 == 0

    def test_clear(self):
        """Test clearing repository."""
        repo = InMemoryExecutionCounterRepository()
        repo.get_next_index("20240101", "alice", "chip_1", "proj-1")

        repo.clear()

        # After clear, should start at 0 again
        index = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        assert index == 0


class TestInMemoryExecutionLockRepository:
    """Test InMemoryExecutionLockRepository."""

    def test_is_locked_default_false(self):
        """Test lock is False by default."""
        repo = InMemoryExecutionLockRepository()
        assert not repo.is_locked("proj-1")

    def test_lock_and_is_locked(self):
        """Test locking project."""
        repo = InMemoryExecutionLockRepository()

        repo.lock("proj-1")

        assert repo.is_locked("proj-1")

    def test_unlock(self):
        """Test unlocking project."""
        repo = InMemoryExecutionLockRepository()
        repo.lock("proj-1")

        repo.unlock("proj-1")

        assert not repo.is_locked("proj-1")

    def test_different_projects_independent(self):
        """Test different projects have independent locks."""
        repo = InMemoryExecutionLockRepository()

        repo.lock("proj-1")

        assert repo.is_locked("proj-1")
        assert not repo.is_locked("proj-2")

    def test_clear(self):
        """Test clearing repository."""
        repo = InMemoryExecutionLockRepository()
        repo.lock("proj-1")

        repo.clear()

        assert not repo.is_locked("proj-1")


class TestInMemoryUserRepository:
    """Test InMemoryUserRepository."""

    def test_get_default_project_id_not_found(self):
        """Test getting project ID for non-existent user."""
        repo = InMemoryUserRepository()
        result = repo.get_default_project_id("nonexistent")
        assert result is None

    def test_add_user_and_get_project_id(self):
        """Test adding user and getting project ID."""
        repo = InMemoryUserRepository()

        repo.add_user("alice", default_project_id="proj-1")
        result = repo.get_default_project_id("alice")

        assert result == "proj-1"

    def test_add_user_without_project_id(self):
        """Test adding user without project ID."""
        repo = InMemoryUserRepository()

        repo.add_user("alice")
        result = repo.get_default_project_id("alice")

        assert result is None

    def test_clear(self):
        """Test clearing repository."""
        repo = InMemoryUserRepository()
        repo.add_user("alice", default_project_id="proj-1")

        repo.clear()

        assert repo.get_default_project_id("alice") is None


class TestInMemoryTaskRepository:
    """Test InMemoryTaskRepository."""

    def test_get_task_names_empty(self):
        """Test getting tasks for non-existent user."""
        repo = InMemoryTaskRepository()
        result = repo.get_task_names("nonexistent")
        assert result == []

    def test_add_tasks_and_get(self):
        """Test adding and getting tasks."""
        repo = InMemoryTaskRepository()

        repo.add_tasks("alice", ["CheckFreq", "CheckRabi"])
        result = repo.get_task_names("alice")

        assert "CheckFreq" in result
        assert "CheckRabi" in result

    def test_different_users_have_separate_tasks(self):
        """Test different users have separate task lists."""
        repo = InMemoryTaskRepository()

        repo.add_tasks("alice", ["CheckFreq"])
        repo.add_tasks("bob", ["CheckRabi"])

        assert repo.get_task_names("alice") == ["CheckFreq"]
        assert repo.get_task_names("bob") == ["CheckRabi"]

    def test_clear(self):
        """Test clearing repository."""
        repo = InMemoryTaskRepository()
        repo.add_tasks("alice", ["CheckFreq"])

        repo.clear()

        assert repo.get_task_names("alice") == []


class TestInMemoryTaskResultHistoryRepository:
    """Test InMemoryTaskResultHistoryRepository."""

    def test_save_and_get_all(self):
        """Test saving and retrieving task results."""
        from qdash.datamodel.task import QubitTaskModel
        from qdash.repository.inmemory import InMemoryTaskResultHistoryRepository

        repo = InMemoryTaskResultHistoryRepository()
        execution = ExecutionModel(
            username="alice",
            name="Test",
            execution_id="exec-001",
            calib_data_path="/tmp",
            note={},
            status=ExecutionStatusModel.RUNNING,
            task_results={},
            tags=[],
            chip_id="chip_1",
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data={"qubit": {}, "coupling": {}},
            message="",
            system_info={},
            project_id="proj-1",
        )

        # Create a proper task result model
        task_result = QubitTaskModel(
            name="CheckFreq",
            qid="0",
            project_id="proj-1",
        )

        repo.save(task_result, execution)

        results = repo.get_all()
        assert len(results) == 1
        assert results[0].name == "CheckFreq"
        assert results[0].qid == "0"

    def test_clear(self):
        """Test clearing repository."""
        from qdash.datamodel.task import QubitTaskModel
        from qdash.repository.inmemory import InMemoryTaskResultHistoryRepository

        repo = InMemoryTaskResultHistoryRepository()
        execution = ExecutionModel(
            username="alice",
            name="Test",
            execution_id="exec-001",
            calib_data_path="/tmp",
            note={},
            status=ExecutionStatusModel.RUNNING,
            task_results={},
            tags=[],
            chip_id="chip_1",
            start_at=None,
            end_at=None,
            elapsed_time=None,
            calib_data={"qubit": {}, "coupling": {}},
            message="",
            system_info={},
            project_id="proj-1",
        )
        task_result = QubitTaskModel(name="Test", qid="0", project_id="proj-1")
        repo.save(task_result, execution)

        repo.clear()

        assert repo.get_all() == []


class TestInMemoryChipHistoryRepository:
    """Test InMemoryChipHistoryRepository."""

    def test_create_history(self):
        """Test creating chip history snapshot."""
        from qdash.repository.inmemory import InMemoryChipHistoryRepository

        repo = InMemoryChipHistoryRepository()

        repo.create_history("alice", "chip_1")

        history = repo.get_all()
        assert len(history) == 1
        assert history[0]["username"] == "alice"
        assert history[0]["chip_id"] == "chip_1"

    def test_create_history_without_chip_id(self):
        """Test creating history without chip_id."""
        from qdash.repository.inmemory import InMemoryChipHistoryRepository

        repo = InMemoryChipHistoryRepository()

        repo.create_history("alice")

        history = repo.get_all()
        assert len(history) == 1
        assert history[0]["username"] == "alice"
        assert history[0]["chip_id"] is None

    def test_clear(self):
        """Test clearing repository."""
        from qdash.repository.inmemory import InMemoryChipHistoryRepository

        repo = InMemoryChipHistoryRepository()
        repo.create_history("alice", "chip_1")

        repo.clear()

        assert repo.get_all() == []


class TestInMemoryQubitCalibrationRepository:
    """Test InMemoryQubitCalibrationRepository."""

    def test_update_calib_data_creates_new(self):
        """Test updating creates new qubit if not exists."""
        from qdash.repository.inmemory import InMemoryQubitCalibrationRepository

        repo = InMemoryQubitCalibrationRepository()

        result = repo.update_calib_data(
            username="alice",
            qid="0",
            chip_id="chip_1",
            output_parameters={"qubit_frequency": {"value": 5.0}},
            project_id="proj-1",
        )

        assert result is not None
        assert result.qid == "0"
        assert result.data["qubit_frequency"]["value"] == 5.0

    def test_update_calib_data_merges_existing(self):
        """Test updating merges into existing qubit."""
        from qdash.repository.inmemory import InMemoryQubitCalibrationRepository

        repo = InMemoryQubitCalibrationRepository()

        # First update
        repo.update_calib_data(
            username="alice",
            qid="0",
            chip_id="chip_1",
            output_parameters={"qubit_frequency": {"value": 5.0}},
            project_id="proj-1",
        )

        # Second update
        result = repo.update_calib_data(
            username="alice",
            qid="0",
            chip_id="chip_1",
            output_parameters={"t1": {"value": 100.0}},
            project_id="proj-1",
        )

        assert result.data["qubit_frequency"]["value"] == 5.0
        assert result.data["t1"]["value"] == 100.0

    def test_find_one(self):
        """Test finding qubit by identifiers."""
        from qdash.repository.inmemory import InMemoryQubitCalibrationRepository

        repo = InMemoryQubitCalibrationRepository()
        repo.update_calib_data(
            username="alice",
            qid="0",
            chip_id="chip_1",
            output_parameters={"qubit_frequency": {"value": 5.0}},
            project_id="proj-1",
        )

        found = repo.find_one(username="alice", qid="0", chip_id="chip_1")
        not_found = repo.find_one(username="bob", qid="0", chip_id="chip_1")

        assert found is not None
        assert found.qid == "0"
        assert not_found is None

    def test_clear(self):
        """Test clearing repository."""
        from qdash.repository.inmemory import InMemoryQubitCalibrationRepository

        repo = InMemoryQubitCalibrationRepository()
        repo.update_calib_data(
            username="alice",
            qid="0",
            chip_id="chip_1",
            output_parameters={"qubit_frequency": {"value": 5.0}},
            project_id="proj-1",
        )

        repo.clear()

        assert repo.find_one(username="alice", qid="0", chip_id="chip_1") is None


class TestInMemoryCouplingCalibrationRepository:
    """Test InMemoryCouplingCalibrationRepository."""

    def test_update_calib_data_creates_new(self):
        """Test updating creates new coupling if not exists."""
        from qdash.repository.inmemory import InMemoryCouplingCalibrationRepository

        repo = InMemoryCouplingCalibrationRepository()

        result = repo.update_calib_data(
            username="alice",
            qid="0-1",
            chip_id="chip_1",
            output_parameters={"zx90_gate_fidelity": {"value": 0.99}},
            project_id="proj-1",
        )

        assert result is not None
        assert result.qid == "0-1"
        assert result.data["zx90_gate_fidelity"]["value"] == 0.99

    def test_update_calib_data_merges_existing(self):
        """Test updating merges into existing coupling."""
        from qdash.repository.inmemory import InMemoryCouplingCalibrationRepository

        repo = InMemoryCouplingCalibrationRepository()

        # First update
        repo.update_calib_data(
            username="alice",
            qid="0-1",
            chip_id="chip_1",
            output_parameters={"zx90_gate_fidelity": {"value": 0.99}},
            project_id="proj-1",
        )

        # Second update
        result = repo.update_calib_data(
            username="alice",
            qid="0-1",
            chip_id="chip_1",
            output_parameters={"cr_amplitude": {"value": 0.5}},
            project_id="proj-1",
        )

        assert result.data["zx90_gate_fidelity"]["value"] == 0.99
        assert result.data["cr_amplitude"]["value"] == 0.5

    def test_find_one(self):
        """Test finding coupling by identifiers."""
        from qdash.repository.inmemory import InMemoryCouplingCalibrationRepository

        repo = InMemoryCouplingCalibrationRepository()
        repo.update_calib_data(
            username="alice",
            qid="0-1",
            chip_id="chip_1",
            output_parameters={"zx90_gate_fidelity": {"value": 0.99}},
            project_id="proj-1",
        )

        found = repo.find_one(username="alice", qid="0-1", chip_id="chip_1")
        not_found = repo.find_one(username="bob", qid="0-1", chip_id="chip_1")

        assert found is not None
        assert found.qid == "0-1"
        assert not_found is None

    def test_clear(self):
        """Test clearing repository."""
        from qdash.repository.inmemory import InMemoryCouplingCalibrationRepository

        repo = InMemoryCouplingCalibrationRepository()
        repo.update_calib_data(
            username="alice",
            qid="0-1",
            chip_id="chip_1",
            output_parameters={"zx90_gate_fidelity": {"value": 0.99}},
            project_id="proj-1",
        )

        repo.clear()

        assert repo.find_one(username="alice", qid="0-1", chip_id="chip_1") is None
