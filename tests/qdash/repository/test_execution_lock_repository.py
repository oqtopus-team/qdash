"""Tests for MongoExecutionLockRepository."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.repository.execution_lock import MongoExecutionLockRepository
from qdash.repository.inmemory.execution_lock import InMemoryExecutionLockRepository

if TYPE_CHECKING:
    from qdash.repository.protocols import ExecutionLockRepository

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


def test_non_conflicting_resource_claims_run_concurrently(init_db: object) -> None:
    repo = MongoExecutionLockRepository()

    assert repo.try_lock(PROJECT_ID, "exec-1", "chip-1", ("mux:0",), False)
    assert repo.try_lock(PROJECT_ID, "exec-2", "chip-1", ("mux:1",), False)

    doc = _reload_lock()
    assert doc is not None
    assert {claim.execution_id for claim in doc.claims} == {"exec-1", "exec-2"}


def test_overlapping_resource_claim_is_rejected(init_db: object) -> None:
    repo = MongoExecutionLockRepository()

    assert repo.try_lock(PROJECT_ID, "exec-1", "chip-1", ("channel:box-1",), False)
    assert not repo.try_lock(PROJECT_ID, "exec-2", "chip-1", ("channel:box-1",), False)


def test_unlock_releases_only_the_owning_execution(init_db: object) -> None:
    repo = MongoExecutionLockRepository()
    repo.try_lock(PROJECT_ID, "exec-1", "chip-1", ("mux:0",), False)
    repo.try_lock(PROJECT_ID, "exec-2", "chip-1", ("mux:1",), False)

    repo.unlock(PROJECT_ID, "exec-1")

    doc = _reload_lock()
    assert doc is not None
    assert doc.locked is True
    assert [claim.execution_id for claim in doc.claims] == ["exec-2"]


@pytest.fixture(params=["mongo", "inmemory"])
def resource_repo(request: pytest.FixtureRequest, init_db: object) -> ExecutionLockRepository:
    if request.param == "mongo":
        return MongoExecutionLockRepository()
    return InMemoryExecutionLockRepository()


def test_anonymous_claim_cannot_be_reacquired(resource_repo: ExecutionLockRepository) -> None:
    assert resource_repo.try_lock(PROJECT_ID)
    assert not resource_repo.try_lock(PROJECT_ID)
    assert not resource_repo.try_lock(PROJECT_ID, "other", "chip-1", ("mux:0",), False)


def test_legacy_lock_blocks_new_claims(resource_repo: ExecutionLockRepository) -> None:
    resource_repo.lock(PROJECT_ID, "owner")
    assert not resource_repo.try_lock(PROJECT_ID, "other", "chip-1", ("mux:0",), False)
    assert resource_repo.try_lock(PROJECT_ID, "owner", "chip-1", ("mux:0",), False)
    # Reacquisition must preserve the original project-wide reservation.
    assert not resource_repo.try_lock(PROJECT_ID, "other", "chip-2", ("mux:1",), False)
    resource_repo.unlock(PROJECT_ID, "other")
    assert resource_repo.is_locked(PROJECT_ID)
    resource_repo.unlock(PROJECT_ID, "owner")
    assert resource_repo.try_lock(PROJECT_ID, "other", "chip-1", ("mux:0",), False)


def test_expansion_rechecks_conflicts_and_preserves_claims(
    resource_repo: ExecutionLockRepository,
) -> None:
    assert resource_repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:0",), False)
    assert resource_repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:1",), False)
    assert not resource_repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:0", "mux:1"), False)
    assert not resource_repo.try_lock(PROJECT_ID, "A", "chip-1", (), True)
    resource_repo.unlock(PROJECT_ID, "B")
    assert resource_repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:1",), False)
    assert not resource_repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:0",), False)
    assert not resource_repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:1",), False)
    resource_repo.unlock(PROJECT_ID, "A")
    assert resource_repo.try_lock(PROJECT_ID, "B", "chip-1", (), True)


def test_reacquisition_preserves_chip_exclusivity(resource_repo: ExecutionLockRepository) -> None:
    assert resource_repo.try_lock(PROJECT_ID, "A", "chip-1", (), True)
    assert resource_repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:0",), False)
    assert not resource_repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:1",), False)
    assert resource_repo.try_lock(PROJECT_ID, "B", "chip-2", ("mux:1",), False)


def test_expansion_to_another_chip_checks_and_retains_both_scopes(
    resource_repo: ExecutionLockRepository,
) -> None:
    assert resource_repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:0",), False)
    assert resource_repo.try_lock(PROJECT_ID, "B", "chip-2", ("mux:0",), False)
    assert not resource_repo.try_lock(PROJECT_ID, "A", "chip-2", ("mux:0",), False)
    resource_repo.unlock(PROJECT_ID, "B")
    assert resource_repo.try_lock(PROJECT_ID, "A", "chip-2", ("mux:0",), False)
    assert not resource_repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:0",), False)
    assert not resource_repo.try_lock(PROJECT_ID, "B", "chip-2", ("mux:0",), False)


def test_legacy_record_without_claims_preserves_ownership(init_db: object) -> None:
    collection = ExecutionLockDocument.get_motor_collection()
    collection.insert_one({"project_id": PROJECT_ID, "locked": True, "execution_id": "A"})
    repo = MongoExecutionLockRepository()
    assert not repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:0",), False)
    assert repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:0",), False)
    assert not repo.try_lock(PROJECT_ID, "B", "chip-2", ("mux:0",), False)
    repo.unlock(PROJECT_ID, "A")
    assert repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:0",), False)


def test_reacquisition_does_not_trust_stale_owner_snapshot(
    init_db: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MongoExecutionLockRepository()
    assert repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:0",), False)
    stale_owner = _reload_lock()
    repo.unlock(PROJECT_ID, "A")
    assert repo.try_lock(PROJECT_ID, "B", "chip-1", ("mux:0",), False)
    # Model a read of A's ownership that completed before release and B's acquisition.
    stale_read = MagicMock()
    stale_read.run.return_value = stale_owner
    monkeypatch.setattr(ExecutionLockDocument, "find_one", lambda *args, **kwargs: stale_read)
    assert not repo.try_lock(PROJECT_ID, "A", "chip-1", ("mux:0",), False)
    raw = ExecutionLockDocument.get_motor_collection().find_one({"project_id": PROJECT_ID})
    assert raw is not None
    assert [claim["execution_id"] for claim in raw["claims"]] == ["B"]
