"""``prepare-run-scope`` drops the earlier run index only when the replacement is right and
nothing is in flight, and changes nothing else.

The tests use an in-memory MongoDB by default. Set ``QDASH_MIGRATION_TEST_MONGO_URI`` to a
disposable MongoDB server to run the same tests against it; each test uses a database of its
own and drops it afterwards. Never point it at a server holding real data.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import mongomock
import pytest
from pymongo import ASCENDING, MongoClient
from pymongo.errors import DuplicateKeyError

import qdash.dbmodel.migration as migration
from qdash.dbmodel.migration import MigrationError, migrate_prepare_run_scope
from qdash.dbmodel.run import LEGACY_SESSION_KEY_INDEX, RUN_COLLECTION, RUN_SCOPE_INDEX

if TYPE_CHECKING:
    from collections.abc import Generator

    from pymongo.database import Database

LEGACY_KEYS = [
    ("project_id", ASCENDING),
    ("calibration_session_id", ASCENDING),
    ("idempotency_key", ASCENDING),
]
SCOPE_KEYS = [("project_id", ASCENDING), ("idempotency_scope", ASCENDING)]
SCOPE_FILTER = {"idempotency_scope": {"$type": "string"}}


@pytest.fixture
def db() -> Generator[Database[Any], None, None]:
    uri = os.getenv("QDASH_MIGRATION_TEST_MONGO_URI")
    client: Any = MongoClient(uri) if uri else mongomock.MongoClient()
    name = f"qdash_prepare_run_scope_{uuid4().hex[:12]}"
    try:
        yield client[name]
    finally:
        client.drop_database(name)
        client.close()


def _ago(**delta: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**delta)


def _legacy_index(db: Database[Any], **options: Any) -> None:
    db[RUN_COLLECTION].create_index(
        LEGACY_KEYS, name=LEGACY_SESSION_KEY_INDEX, **{"unique": True, **options}
    )


def _scope_index(db: Database[Any], keys: Any = None, **options: Any) -> None:
    spec = {"unique": True, "partialFilterExpression": SCOPE_FILTER, **options}
    db[RUN_COLLECTION].create_index(
        keys or SCOPE_KEYS, name=RUN_SCOPE_INDEX, **{k: v for k, v in spec.items() if v is not None}
    )


def _run(db: Database[Any], run_id: str, **fields: Any) -> None:
    db[RUN_COLLECTION].insert_one(
        {
            "run_id": run_id,
            "project_id": "p",
            "calibration_session_id": None,
            "idempotency_key": run_id,
            "idempotency_scope": f"key:{run_id}",
            "status": "dispatched",
            "requested_at": _ago(hours=2),
            "updated_at": _ago(hours=2),
            **fields,
        }
    )


def _snapshot(db: Database[Any]) -> dict[str, Any]:
    return {
        name: sorted(
            (repr(sorted((k, v) for k, v in doc.items() if k != "_id")))
            for doc in db[name].find({})
        )
        for name in (RUN_COLLECTION, "calibration_sessions", "agent_sessions")
    }


def _indexes(db: Database[Any]) -> set[str]:
    return set(db[RUN_COLLECTION].index_information())


@pytest.fixture
def ready_db(db: Database[Any]) -> Database[Any]:
    """The earlier index, this release's index, and only settled runs."""
    _run(db, "r-done")
    _legacy_index(db)
    _scope_index(db)
    return db


class TestReplacementIndex:
    def test_an_absent_replacement_keeps_the_earlier_index(self, db: Database[Any]) -> None:
        _run(db, "r-done")
        _legacy_index(db)
        report = migrate_prepare_run_scope(db, dry_run=True)
        assert report["scope_index_problems"] == ["absent"] and not report["checks_passed"]
        with pytest.raises(MigrationError, match=RUN_SCOPE_INDEX):
            migrate_prepare_run_scope(db, dry_run=False, writers_quiesced=True)
        assert LEGACY_SESSION_KEY_INDEX in _indexes(db)

    @pytest.mark.parametrize(
        ("keys", "options", "problem"),
        [
            pytest.param(
                [("idempotency_scope", ASCENDING), ("project_id", ASCENDING)],
                {},
                "keys are",
                id="key-order",
            ),
            pytest.param([("project_id", ASCENDING)], {}, "keys are", id="missing-key"),
            pytest.param(None, {"unique": None}, "not unique", id="not-unique"),
            pytest.param(None, {"partialFilterExpression": None}, "partial filter", id="no-filter"),
            pytest.param(
                None,
                {"partialFilterExpression": {"idempotency_scope": {"$exists": True}}},
                "partial filter",
                id="other-filter",
            ),
        ],
    )
    def test_a_replacement_with_another_spec_under_its_name_is_refused(
        self, db: Database[Any], keys: Any, options: dict[str, Any], problem: str
    ) -> None:
        _legacy_index(db)
        _scope_index(db, keys, **options)
        report = migrate_prepare_run_scope(db, dry_run=True)
        assert not report["scope_index_valid"]
        assert any(problem in p for p in report["scope_index_problems"])
        with pytest.raises(MigrationError, match="not the one this release creates"):
            migrate_prepare_run_scope(db, dry_run=False, writers_quiesced=True)
        assert LEGACY_SESSION_KEY_INDEX in _indexes(db)

    def test_another_index_under_the_earlier_name_is_never_dropped(self, db: Database[Any]) -> None:
        db[RUN_COLLECTION].create_index(
            [("project_id", ASCENDING), ("idempotency_key", ASCENDING)],
            name=LEGACY_SESSION_KEY_INDEX,
            unique=True,
        )
        _scope_index(db)
        with pytest.raises(MigrationError, match="not the earlier run index"):
            migrate_prepare_run_scope(db, dry_run=False, writers_quiesced=True)
        assert LEGACY_SESSION_KEY_INDEX in _indexes(db)


class TestReadiness:
    @pytest.mark.parametrize(
        ("setup", "count"),
        [
            pytest.param(
                lambda db: _run(db, "r-live", status="dispatching", updated_at=_ago(seconds=5)),
                "dispatching_runs",
                id="dispatching-run",
            ),
            pytest.param(
                lambda db: db["calibration_sessions"].insert_one(
                    {
                        "calibration_session_id": "cs-1",
                        "project_id": "p",
                        "pending_children": [
                            {
                                "reservation_id": "res-1",
                                "kind": "pipeline_run",
                                "child_id": "r-new",
                                "reserved_by": "alice",
                                "reserved_at": _ago(seconds=5),
                            }
                        ],
                    }
                ),
                "pending_children",
                id="pending-child",
            ),
            pytest.param(
                lambda db: db["agent_sessions"].insert_one(
                    {
                        "session_id": "as-1",
                        "project_id": "p",
                        "calibration_admission": "pending",
                        "created_at": _ago(seconds=5),
                        "updated_at": _ago(seconds=5),
                    }
                ),
                "pending_agent_admissions",
                id="pending-agent-admission",
            ),
            pytest.param(
                lambda db: _run(
                    db, "r-old-writer", idempotency_scope=None, requested_at=_ago(seconds=5)
                ),
                "unscoped_run_inserts",
                id="unscoped-insert",
            ),
        ],
    )
    def test_work_in_flight_keeps_the_earlier_index(
        self, ready_db: Database[Any], setup: Any, count: str
    ) -> None:
        setup(ready_db)
        before = _snapshot(ready_db)
        report = migrate_prepare_run_scope(ready_db, dry_run=True)
        assert report["readiness"]["blocked"] and report["readiness"]["counts"][count] == 1
        with pytest.raises(MigrationError, match="in flight"):
            migrate_prepare_run_scope(ready_db, dry_run=False, writers_quiesced=True)
        assert LEGACY_SESSION_KEY_INDEX in _indexes(ready_db)
        assert _snapshot(ready_db) == before

    @pytest.mark.parametrize("kind", ["dispatching", "unadmitted", "unknown", "child", "agent"])
    def test_each_stale_or_unknown_blocker_independently(
        self, ready_db: Database[Any], kind: str
    ) -> None:
        if kind in {"dispatching", "unadmitted", "unknown"}:
            _run(
                ready_db,
                "r-blocker",
                status="unknown" if kind == "unknown" else "dispatching",
                admission="pending" if kind == "unadmitted" else "admitted",
            )
        elif kind == "child":
            ready_db["calibration_sessions"].insert_one(
                {"pending_children": [{"reserved_at": _ago(hours=2)}]}
            )
        else:
            ready_db["agent_sessions"].insert_one(
                {"calibration_admission": "pending", "updated_at": _ago(hours=2)}
            )
        before = (_indexes(ready_db), _snapshot(ready_db))
        report = migrate_prepare_run_scope(ready_db, dry_run=True)
        assert report["readiness"]["blocked"]
        assert sum(report["readiness"]["counts"].values()) == 1
        with pytest.raises(MigrationError, match="unresolved"):
            migrate_prepare_run_scope(ready_db, dry_run=False, writers_quiesced=True)
        assert (_indexes(ready_db), _snapshot(ready_db)) == before

    def test_stale_and_unknown_records_block_the_drop_and_are_left_unchanged(
        self, ready_db: Database[Any]
    ) -> None:
        _run(ready_db, "r-stale", status="dispatching", admission="admitted")
        _run(ready_db, "r-unadmitted", status="dispatching", admission="pending")
        _run(ready_db, "r-unknown", status="unknown")
        _run(ready_db, "r-legacy", idempotency_scope=None, status="rejected")
        ready_db["calibration_sessions"].insert_one(
            {
                "calibration_session_id": "cs-1",
                "project_id": "p",
                "pending_children": [
                    {
                        "reservation_id": "res-1",
                        "kind": "agent_session",
                        "child_id": "as-1",
                        "reserved_by": "alice",
                        "reserved_at": _ago(hours=1),
                    }
                ],
            }
        )
        ready_db["agent_sessions"].insert_one(
            {
                "session_id": "as-1",
                "project_id": "p",
                "calibration_admission": "pending",
                "created_at": _ago(hours=1),
                "updated_at": _ago(hours=1),
            }
        )
        before = _snapshot(ready_db)
        stats = migrate_prepare_run_scope(ready_db, dry_run=True, writers_quiesced=True)
        assert stats["dropped"] is False
        assert stats["readiness"]["blocked"] is True
        with pytest.raises(MigrationError, match="unresolved"):
            migrate_prepare_run_scope(ready_db, dry_run=False, writers_quiesced=True)
        assert LEGACY_SESSION_KEY_INDEX in ready_db[RUN_COLLECTION].index_information()
        assert stats["readiness"]["counts"] == {
            "dispatching_runs": 0,
            "pending_children": 0,
            "pending_agent_admissions": 0,
            "unscoped_run_inserts": 0,
            "stale_dispatching_runs": 1,
            "stale_unadmitted_runs": 1,
            "unknown_runs": 1,
            "stale_pending_children": 1,
            "stale_pending_agent_admissions": 1,
        }
        assert stats["readiness"]["unresolved_stale_or_unknown"]["unknown_runs"] == ["p/r-unknown"]
        # Nothing is cleared, settled, or rewritten to pass.
        assert _snapshot(ready_db) == before

    def test_work_started_after_the_first_read_stops_the_drop(
        self, ready_db: Database[Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads = 0
        real = migration._run_scope_readiness

        def readiness(database: Database[Any], *, at: datetime) -> dict[str, Any]:
            nonlocal reads
            reads += 1
            if reads == 2:
                _run(database, "r-late", status="dispatching", updated_at=_ago(seconds=1))
            return real(database, at=at)

        monkeypatch.setattr(migration, "_run_scope_readiness", readiness)
        with pytest.raises(MigrationError, match="recheck before the drop"):
            migrate_prepare_run_scope(ready_db, dry_run=False, writers_quiesced=True)
        assert LEGACY_SESSION_KEY_INDEX in _indexes(ready_db)


class TestExecution:
    def test_a_dry_run_changes_nothing(self, ready_db: Database[Any]) -> None:
        before = (_indexes(ready_db), _snapshot(ready_db))
        report = migrate_prepare_run_scope(ready_db, dry_run=True, writers_quiesced=True)
        assert report["ready"] and not report["dropped"]
        assert (_indexes(ready_db), _snapshot(ready_db)) == before

    def test_execution_requires_the_quiescence_acknowledgement(
        self, ready_db: Database[Any]
    ) -> None:
        report = migrate_prepare_run_scope(ready_db, dry_run=True)
        assert report["checks_passed"] and not report["ready"]
        with pytest.raises(MigrationError, match="writers-quiesced"):
            migrate_prepare_run_scope(ready_db, dry_run=False)
        assert LEGACY_SESSION_KEY_INDEX in _indexes(ready_db)

    def test_it_drops_only_the_earlier_index_and_a_rerun_does_nothing(
        self, ready_db: Database[Any]
    ) -> None:
        before = _snapshot(ready_db)
        stats = migrate_prepare_run_scope(ready_db, dry_run=False, writers_quiesced=True)
        assert stats["dropped"] is True
        assert _indexes(ready_db) == {"_id_", RUN_SCOPE_INDEX}
        assert _snapshot(ready_db) == before
        rerun = migrate_prepare_run_scope(ready_db, dry_run=False, writers_quiesced=True)
        assert rerun["dropped"] is False and rerun["already_dropped"] is True
        assert _indexes(ready_db) == {"_id_", RUN_SCOPE_INDEX}

    def test_after_the_drop_two_users_may_use_one_key_without_a_session(
        self, ready_db: Database[Any]
    ) -> None:
        migrate_prepare_run_scope(ready_db, dry_run=False, writers_quiesced=True)
        _run(ready_db, "r-a", idempotency_key="k", idempotency_scope="key:alice-k")
        _run(ready_db, "r-b", idempotency_key="k", idempotency_scope="key:bob-k")
        # The scope index still refuses a second run in one scope.
        with pytest.raises(DuplicateKeyError):
            _run(ready_db, "r-a2", idempotency_key="k", idempotency_scope="key:alice-k")
