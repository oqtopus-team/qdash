"""Regression coverage for cross-chip execution ID collisions and upgrades."""

from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from threading import RLock

import pytest

from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.project_execution_counter import ProjectExecutionCounterDocument
from qdash.repository.execution_counter import MongoExecutionCounterRepository


@pytest.fixture(autouse=True)
def atomic_mock_writes(init_db, monkeypatch):
    # MongoDB makes each write atomic; mongomock's multi-step implementation
    # needs a lock to provide that same guarantee in threaded regression tests.
    collection = init_db.project_execution_counter
    lock = RLock()

    def synchronized(method):
        @wraps(method)
        def call(*args, **kwargs):
            with lock:
                return method(*args, **kwargs)

        return call

    for name in ("update_one", "find_one_and_update"):
        monkeypatch.setattr(collection, name, synchronized(getattr(collection, name)))


def allocate(chip="chip-a", project="project", date="20261027"):
    return ProjectExecutionCounterDocument.get_next_index(date, "alice", chip, project, "user")


def test_chips_share_counter_but_projects_and_dates_do_not(init_db):
    assert allocate() == 0
    assert allocate("chip-b") == 1
    assert allocate() == 2
    assert allocate(project="other") == 0
    assert allocate(date="20261028") == 0


def test_parallel_first_allocations_share_one_counter(init_db):
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda i: allocate(f"chip-{i % 4}"), range(64)))
    assert sorted(values) == list(range(64))
    assert init_db.project_execution_counter.count_documents({}) == 1


@pytest.mark.parametrize("highest_source", ["counter", "execution_history", "task_result_history"])
def test_upgrade_continues_above_all_legacy_ids(init_db, highest_source):
    init_db.execution_counter.insert_many(
        [
            {
                "project_id": "project",
                "date": "20261027",
                "chip_id": chip,
                "index": index,
                "username": "alice",
            }
            for chip, index in [("chip-a", 3), ("chip-b", 12)]
        ]
    )
    if highest_source != "counter":
        init_db[highest_source].insert_one(
            {"project_id": "project", "execution_id": "20261027-1000", "chip_id": "chip-c"}
        )
    # Other projects/dates and malformed IDs must not influence this allocation.
    init_db.task_result_history.insert_many(
        [
            {"project_id": "other", "execution_id": "20261027-9999", "task_id": "other"},
            {"project_id": "project", "execution_id": "20261028-9999", "task_id": "tomorrow"},
            {"project_id": "project", "execution_id": "20261027-invalid", "task_id": "invalid"},
        ]
    )
    expected = 13 if highest_source == "counter" else 1001
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda i: allocate(f"chip-{i}"), range(12)))
    assert sorted(values) == list(range(expected, expected + 12))
    assert init_db.execution_counter.count_documents({}) == 2


def test_chip_dates_include_legacy_and_shared_counters(init_db, monkeypatch):
    init_db.execution_counter.insert_one(
        {
            "project_id": "project",
            "date": "20261026",
            "chip_id": "chip-a",
            "index": 2,
            "username": "alice",
        }
    )
    monkeypatch.setattr(
        MongoExecutionCounterRepository, "_user_id_for_username", staticmethod(lambda _: "user")
    )
    repo = MongoExecutionCounterRepository()
    assert repo.get_next_index("20261027", "alice", "chip-a", "project") == 0
    assert repo.get_next_index("20261027", "bob", "chip-b", "project") == 1
    assert repo.get_dates_for_chip("project", "chip-a") == ["20261026", "20261027"]
    assert repo.get_dates_for_chip("project", "chip-b") == ["20261027"]
    assert repo.get_dates_for_chip("other", "chip-a") == []
    assert repo.get_dates_for_chip("project", "unused") == []


def test_legacy_entry_point_uses_shared_allocator(init_db):
    assert (
        ExecutionCounterDocument.get_next_index("20261027", "alice", "chip-a", "project", "u") == 0
    )
    assert allocate("chip-b") == 1
