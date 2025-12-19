"""Tests for InMemory repository implementations."""

import pytest

from qdash.datamodel.execution import (
    ExecutionModel,
    ExecutionStatusModel,
)
from qdash.workflow.engine.repository import (
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
