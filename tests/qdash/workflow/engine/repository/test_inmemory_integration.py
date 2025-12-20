"""Integration tests using InMemory repository implementations.

These tests verify that services work correctly with InMemory implementations,
enabling MongoDB-free testing of workflow logic.
"""

import pytest
from qdash.datamodel.execution import ExecutionModel, ExecutionStatusModel
from qdash.workflow.engine.repository import (
    InMemoryExecutionCounterRepository,
    InMemoryExecutionLockRepository,
    InMemoryExecutionRepository,
    InMemoryTaskRepository,
    InMemoryUserRepository,
)


class TestGenerateExecutionIdWithInMemory:
    """Test execution ID generation with InMemory counter repository."""

    def test_generate_execution_id_increments(self):
        """Test that execution IDs increment correctly."""
        from qdash.workflow.service.calib_service import generate_execution_id

        counter_repo = InMemoryExecutionCounterRepository()

        # Generate multiple IDs for the same date/user/chip/project
        id1 = generate_execution_id(
            username="alice",
            chip_id="chip_1",
            project_id="proj-1",
            counter_repo=counter_repo,
        )
        id2 = generate_execution_id(
            username="alice",
            chip_id="chip_1",
            project_id="proj-1",
            counter_repo=counter_repo,
        )
        id3 = generate_execution_id(
            username="alice",
            chip_id="chip_1",
            project_id="proj-1",
            counter_repo=counter_repo,
        )

        # IDs should have incrementing indices
        assert id1.endswith("-000")
        assert id2.endswith("-001")
        assert id3.endswith("-002")

    def test_generate_execution_id_different_users_independent(self):
        """Test that different users have independent counters."""
        from qdash.workflow.service.calib_service import generate_execution_id

        counter_repo = InMemoryExecutionCounterRepository()

        id_alice = generate_execution_id(
            username="alice",
            chip_id="chip_1",
            project_id="proj-1",
            counter_repo=counter_repo,
        )
        id_bob = generate_execution_id(
            username="bob",
            chip_id="chip_1",
            project_id="proj-1",
            counter_repo=counter_repo,
        )

        # Both should start at 000
        assert id_alice.endswith("-000")
        assert id_bob.endswith("-000")


class TestExecutionLockWithInMemory:
    """Test execution locking with InMemory lock repository."""

    def test_lock_prevents_concurrent_execution(self):
        """Test that locking works correctly."""
        lock_repo = InMemoryExecutionLockRepository()

        # Initially not locked
        assert not lock_repo.is_locked("proj-1")

        # Lock the project
        lock_repo.lock("proj-1")
        assert lock_repo.is_locked("proj-1")

        # Other project still unlocked
        assert not lock_repo.is_locked("proj-2")

        # Unlock
        lock_repo.unlock("proj-1")
        assert not lock_repo.is_locked("proj-1")


class TestUserRepositoryWithInMemory:
    """Test user repository with InMemory implementation."""

    def test_get_default_project_id(self):
        """Test getting default project ID."""
        user_repo = InMemoryUserRepository()

        # Initially no user
        assert user_repo.get_default_project_id("alice") is None

        # Add user with project
        user_repo.add_user("alice", default_project_id="proj-1")
        assert user_repo.get_default_project_id("alice") == "proj-1"


class TestTaskValidationWithInMemory:
    """Test task validation with InMemory task repository."""

    def test_validate_task_name_success(self):
        """Test successful task name validation."""
        from qdash.workflow.engine.task_runner import validate_task_name

        task_repo = InMemoryTaskRepository()
        task_repo.add_tasks("alice", ["CheckFreq", "CheckRabi", "CheckT1"])

        # Should not raise for valid tasks
        result = validate_task_name(
            task_names=["CheckFreq", "CheckRabi"],
            username="alice",
            task_repo=task_repo,
        )
        assert result == ["CheckFreq", "CheckRabi"]

    def test_validate_task_name_fails_for_invalid(self):
        """Test that validation fails for invalid task names."""
        from qdash.workflow.engine.task_runner import validate_task_name

        task_repo = InMemoryTaskRepository()
        task_repo.add_tasks("alice", ["CheckFreq"])

        with pytest.raises(ValueError, match="Invalid task name"):
            validate_task_name(
                task_names=["InvalidTask"],
                username="alice",
                task_repo=task_repo,
            )


class TestExecutionRepositoryWithInMemory:
    """Test execution repository with InMemory implementation."""

    def test_execution_lifecycle(self):
        """Test full execution lifecycle with InMemory repository."""
        repo = InMemoryExecutionRepository()

        # Create execution
        model = ExecutionModel(
            username="alice",
            name="Test Calibration",
            execution_id="20240101-alice-chip_1-proj-1-000",
            calib_data_path="/tmp/calib",
            note={},
            status=ExecutionStatusModel.SCHEDULED,
            task_results={},
            tags=["test"],
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

        # Save
        repo.save(model)

        # Find
        found = repo.find_by_id("20240101-alice-chip_1-proj-1-000")
        assert found is not None
        assert found.status == ExecutionStatusModel.SCHEDULED

        # Update status
        def update_to_running(m: ExecutionModel) -> None:
            m.status = ExecutionStatusModel.RUNNING

        updated = repo.update_with_optimistic_lock(
            "20240101-alice-chip_1-proj-1-000",
            update_to_running,
        )
        assert updated.status == ExecutionStatusModel.RUNNING

        # Verify update persisted
        found_again = repo.find_by_id("20240101-alice-chip_1-proj-1-000")
        assert found_again is not None
        assert found_again.status == ExecutionStatusModel.RUNNING


class TestRepositoryIsolation:
    """Test that repositories are properly isolated."""

    def test_repositories_have_independent_state(self):
        """Test that different repository instances are independent."""
        repo1 = InMemoryExecutionCounterRepository()
        repo2 = InMemoryExecutionCounterRepository()

        # Modify repo1
        repo1.get_next_index("20240101", "alice", "chip_1", "proj-1")
        repo1.get_next_index("20240101", "alice", "chip_1", "proj-1")

        # repo2 should start fresh
        index = repo2.get_next_index("20240101", "alice", "chip_1", "proj-1")
        assert index == 0  # Independent counter

    def test_clear_resets_state(self):
        """Test that clear() properly resets repository state."""
        repo = InMemoryExecutionRepository()
        model = ExecutionModel(
            username="alice",
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

        # Clear
        repo.clear()

        # Should be empty
        assert repo.find_by_id("exec-001") is None
