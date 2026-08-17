"""Tests for MongoExecutionRepository.claim_scheduled_execution."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import mongomock
import pytest

from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.repository.execution import MongoExecutionRepository

PROJECT_ID = "proj-1"
FLOW_RUN_ID = "flow-run-1"
DATABASE_NAME = "qdash_test"


@pytest.fixture
def repository() -> MongoExecutionRepository:
    """Build a MongoExecutionRepository pointed at an explicit test database name."""
    return MongoExecutionRepository(database=DATABASE_NAME)


def _collection_for(client: mongomock.MongoClient) -> Any:
    """Return the execution history collection within the given mongomock client."""
    return client[DATABASE_NAME][ExecutionHistoryDocument.Settings.name]


def _insert_execution(
    client: mongomock.MongoClient,
    *,
    execution_id: str = "exec-1",
    project_id: str | None = PROJECT_ID,
    flow_run_id: str | None = FLOW_RUN_ID,
    status: str = "scheduled",
    claimed: bool = False,
) -> dict[str, Any]:
    """Insert a plain-dict execution fixture directly into the mongomock collection."""
    note: dict[str, Any] = {}
    if flow_run_id is not None:
        note["flow_run_id"] = flow_run_id
    if claimed:
        note["claimed_at"] = "already-claimed"
    doc = {
        "project_id": project_id,
        "execution_id": execution_id,
        "status": status,
        "note": note,
    }
    _collection_for(client).insert_one(doc)
    return doc


def test_claims_matching_scheduled_execution(repository: MongoExecutionRepository) -> None:
    """A matching scheduled, unclaimed execution is claimed and stamped with claimed_at."""
    client: mongomock.MongoClient = mongomock.MongoClient()
    _insert_execution(client)

    with patch.object(repository, "_get_client", return_value=client):
        claimed_id = repository.claim_scheduled_execution(
            project_id=PROJECT_ID, flow_run_id=FLOW_RUN_ID
        )

    assert claimed_id == "exec-1"
    stored = _collection_for(client).find_one({"execution_id": "exec-1"})
    assert stored is not None
    assert stored["note"]["claimed_at"] is not None


@pytest.mark.parametrize(
    "insert_kwargs",
    [
        pytest.param({"flow_run_id": "other-flow-run"}, id="different-flow-run-id"),
        pytest.param({"claimed": True}, id="already-claimed"),
        pytest.param({"status": "running"}, id="not-scheduled"),
        pytest.param({"project_id": "other-project"}, id="different-project"),
    ],
)
def test_returns_none_when_nothing_matches(
    repository: MongoExecutionRepository, insert_kwargs: dict[str, Any]
) -> None:
    """No matching row means claim_scheduled_execution returns None without raising."""
    client: mongomock.MongoClient = mongomock.MongoClient()
    _insert_execution(client, **insert_kwargs)

    with patch.object(repository, "_get_client", return_value=client):
        claimed_id = repository.claim_scheduled_execution(
            project_id=PROJECT_ID, flow_run_id=FLOW_RUN_ID
        )

    assert claimed_id is None


def test_returns_none_when_mongo_call_raises(repository: MongoExecutionRepository) -> None:
    """A mongo failure is swallowed and reported as None instead of being raised."""
    with patch.object(repository, "_get_client", side_effect=RuntimeError("boom")):
        claimed_id = repository.claim_scheduled_execution(
            project_id=PROJECT_ID, flow_run_id=FLOW_RUN_ID
        )

    assert claimed_id is None
