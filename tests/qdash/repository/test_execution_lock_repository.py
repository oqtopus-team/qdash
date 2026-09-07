"""Tests for MongoExecutionLockRepository."""

from __future__ import annotations

from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.repository.execution_lock import MongoExecutionLockRepository

PROJECT_ID = "proj-1"


def _reload_lock(project_id: str = PROJECT_ID) -> ExecutionLockDocument | None:
    """Reload the ExecutionLockDocument for the given project_id from the database."""
    return ExecutionLockDocument.find_one({"project_id": project_id}).run()


def test_lock_with_execution_id_stores_locked_and_owner(init_db: object) -> None:
    """lock(project_id, execution_id) stores locked=True and records the owning execution."""
    repo = MongoExecutionLockRepository()

    repo.lock(project_id=PROJECT_ID, execution_id="exec-1")

    doc = _reload_lock()
    assert doc is not None
    assert doc.locked is True
    assert doc.execution_id == "exec-1"


def test_lock_without_execution_id_leaves_owner_none(init_db: object) -> None:
    """lock(project_id) without an execution_id leaves the owner as None."""
    repo = MongoExecutionLockRepository()

    repo.lock(project_id=PROJECT_ID)

    doc = _reload_lock()
    assert doc is not None
    assert doc.locked is True
    assert doc.execution_id is None


def test_unlock_clears_locked_and_owner(init_db: object) -> None:
    """unlock(project_id) clears both the locked flag and the recorded owner."""
    repo = MongoExecutionLockRepository()
    repo.lock(project_id=PROJECT_ID, execution_id="exec-1")

    repo.unlock(project_id=PROJECT_ID)

    doc = _reload_lock()
    assert doc is not None
    assert doc.locked is False
    assert doc.execution_id is None


def test_is_locked_reflects_lock_state(init_db: object) -> None:
    """is_locked() reflects whether the project is currently locked."""
    repo = MongoExecutionLockRepository()

    assert repo.is_locked(project_id=PROJECT_ID) is False

    repo.lock(project_id=PROJECT_ID, execution_id="exec-1")
    assert repo.is_locked(project_id=PROJECT_ID) is True

    repo.unlock(project_id=PROJECT_ID)
    assert repo.is_locked(project_id=PROJECT_ID) is False


def test_try_lock_acquires_a_free_lock_and_records_the_owner(init_db: object) -> None:
    """try_lock takes a free lock and records the execution that owns it."""
    repo = MongoExecutionLockRepository()

    assert repo.try_lock(project_id=PROJECT_ID, execution_id="exec-1") is True

    doc = _reload_lock()
    assert doc is not None
    assert doc.locked is True
    assert doc.execution_id == "exec-1"


def test_try_lock_refuses_a_held_lock_and_leaves_the_owner_alone(init_db: object) -> None:
    """A second try_lock is refused and does not overwrite the current owner."""
    repo = MongoExecutionLockRepository()
    repo.try_lock(project_id=PROJECT_ID, execution_id="exec-1")

    assert repo.try_lock(project_id=PROJECT_ID, execution_id="exec-2") is False

    doc = _reload_lock()
    assert doc is not None
    assert doc.locked is True
    assert doc.execution_id == "exec-1"


def test_try_lock_reacquires_a_lock_owned_by_the_same_execution(init_db: object) -> None:
    """The owning execution can take the lock again, which is how a flow adopts it."""
    repo = MongoExecutionLockRepository()
    repo.try_lock(project_id=PROJECT_ID, execution_id="exec-1")

    assert repo.try_lock(project_id=PROJECT_ID, execution_id="exec-1") is True

    doc = _reload_lock()
    assert doc is not None
    assert doc.locked is True
    assert doc.execution_id == "exec-1"


def test_try_lock_succeeds_again_after_unlock(init_db: object) -> None:
    """Releasing the lock lets the next execution take it."""
    repo = MongoExecutionLockRepository()
    repo.try_lock(project_id=PROJECT_ID, execution_id="exec-1")
    repo.unlock(project_id=PROJECT_ID)

    assert repo.try_lock(project_id=PROJECT_ID, execution_id="exec-2") is True

    doc = _reload_lock()
    assert doc is not None
    assert doc.execution_id == "exec-2"


def test_try_lock_is_scoped_to_the_project(init_db: object) -> None:
    """A lock held by one project does not block another."""
    repo = MongoExecutionLockRepository()
    repo.try_lock(project_id=PROJECT_ID, execution_id="exec-1")

    assert repo.try_lock(project_id="proj-2", execution_id="exec-2") is True
