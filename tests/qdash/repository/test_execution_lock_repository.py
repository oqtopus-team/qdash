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
