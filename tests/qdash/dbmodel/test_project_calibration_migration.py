import logging
import os
from datetime import datetime, timezone

import pytest

import qdash.dbmodel.project_calibration_migration as migration_module
from qdash.dbmodel.project_calibration_migration import (
    ARTIFACT_MIGRATION_ID,
    MIGRATION_ID,
    SCOPE_BACKFILL_MIGRATION_ID,
    migrate_calibration_files,
    migrate_project_scoped_calibration,
    run_from_environment,
)


def test_migration_archives_duplicates_and_installs_project_indexes(init_db) -> None:
    qubits = init_db["qubit"]
    counters = init_db["execution_counter"]
    notes = init_db["calibration_note"]
    qubits.drop_indexes()
    counters.drop_indexes()
    notes.drop_indexes()
    legacy_qubit_index = qubits.create_index(
        [("project_id", 1), ("chip_id", 1), ("qid", 1), ("username", 1)],
        unique=True,
    )
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 1, 2, tzinfo=timezone.utc)
    qubits.insert_many(
        [
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "qid": "0",
                "username": "alice",
                "data": {
                    "frequency": {
                        "value": 5.0,
                        "calibrated_at": datetime(2026, 1, 3, tzinfo=timezone.utc),
                    },
                    "t1": {"value": 100.0},
                },
                "system_info": {"created_at": older, "updated_at": older},
            },
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "qid": "0",
                "username": "bob",
                "data": {
                    "frequency": {
                        "value": 5.1,
                        "calibrated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                    }
                },
                "system_info": {"created_at": newer, "updated_at": newer},
            },
        ]
    )
    counters.insert_many(
        [
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "date": "20260102",
                "username": "alice",
                "index": 2,
            },
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "date": "20260102",
                "username": "bob",
                "index": 4,
            },
        ]
    )
    notes.insert_many(
        [
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "execution_id": "20260102-001",
                "task_id": "master",
                "username": "alice",
                "note": {"rabi": {"Q0": {"amplitude": 0.1}}},
                "system_info": {"created_at": older, "updated_at": older},
            },
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "execution_id": "20260102-001",
                "task_id": "master",
                "username": "bob",
                "note": {"rabi": {"Q1": {"amplitude": 0.2}}},
                "system_info": {"created_at": newer, "updated_at": newer},
            },
        ]
    )

    dry_run = migrate_project_scoped_calibration(init_db)
    assert dry_run["collections"]["qubit"]["documents_to_archive"] == 1
    assert qubits.count_documents({}) == 2

    migrate_project_scoped_calibration(init_db, dry_run=False)

    assert qubits.count_documents({}) == 1
    assert qubits.find_one({})["username"] == "bob"
    assert qubits.find_one({})["data"] == {
        "frequency": {
            "value": 5.0,
            "calibrated_at": datetime(2026, 1, 3),
        },
        "t1": {"value": 100.0},
    }
    assert counters.count_documents({}) == 1
    assert counters.find_one({})["index"] == 4
    assert notes.count_documents({}) == 1
    assert notes.find_one({})["username"] == "bob"
    assert notes.find_one({})["note"] == {
        "rabi": {
            "Q0": {"amplitude": 0.1},
            "Q1": {"amplitude": 0.2},
        }
    }
    assert init_db["migration_archive"].count_documents({"migration_id": MIGRATION_ID}) == 3
    assert "project_id_1_chip_id_1_qid_1" in qubits.index_information()
    assert legacy_qubit_index not in qubits.index_information()
    assert "project_id_1_date_1_chip_id_1" in counters.index_information()
    assert "migration_archive_lookup_idx" in init_db["migration_archive"].index_information()
    ledger = init_db["migration_ledger"].find_one({"migration_id": MIGRATION_ID})
    assert ledger["status"] == "completed"
    init_db["migration_archive"].drop_index("migration_archive_lookup_idx")
    repeated = migrate_project_scoped_calibration(init_db, dry_run=False)
    assert repeated["already_completed"] is True
    assert "migration_archive_lookup_idx" in init_db["migration_archive"].index_information()


def test_file_migration_copies_legacy_execution_and_classifier(init_db, tmp_path) -> None:
    execution_source = tmp_path / "alice" / "20260102" / "001"
    execution_source.mkdir(parents=True)
    (execution_source / "result.json").write_text("result")
    classifier_source = tmp_path / "alice" / ".classifier"
    classifier_source.mkdir(parents=True)
    alice_classifier = classifier_source / "model.json"
    alice_classifier.write_text("alice-old")
    bob_classifier_source = tmp_path / "bob" / ".classifier"
    bob_classifier_source.mkdir(parents=True)
    bob_classifier = bob_classifier_source / "model.json"
    bob_classifier.write_text("bob-new")
    os.utime(alice_classifier, (1, 1))
    os.utime(bob_classifier, (2, 2))
    execution_id = (
        init_db["execution_history"]
        .insert_one(
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "execution_id": "20260102-001",
                "username": "alice",
                "calib_data_path": str(execution_source),
            }
        )
        .inserted_id
    )
    task_id = (
        init_db["task_result_history"]
        .insert_one(
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "execution_id": "20260102-001",
                "task_id": "task-1",
                "figure_path": [str(execution_source / "fig" / "result.png")],
                "json_figure_path": [str(execution_source / "fig" / "result.json")],
                "raw_data_path": [str(execution_source / "raw_data" / "result.nc")],
            }
        )
        .inserted_id
    )
    knowledge_id = (
        init_db["issue_knowledge"]
        .insert_one(
            {
                "project_id": "proj-1",
                "task_id": "task-1",
                "figure_paths": [str(execution_source / "fig" / "result.png")],
            }
        )
        .inserted_id
    )
    init_db["chip"].insert_one({"project_id": "proj-1", "chip_id": "chip-1", "username": "alice"})
    init_db["execution_history"].insert_one(
        {
            "project_id": "proj-1",
            "chip_id": "chip-1",
            "execution_id": "20260103-001",
            "username": "bob",
            "calib_data_path": str(tmp_path / "bob" / "20260103" / "001"),
        }
    )

    dry_run = migrate_calibration_files(init_db, base_path=tmp_path)
    assert dry_run["database_records_updated"] == 3
    assert init_db["execution_history"].find_one({"_id": execution_id})["calib_data_path"] == str(
        execution_source
    )
    assert init_db["migration_archive"].count_documents({}) == 0

    stats = migrate_calibration_files(
        init_db, base_path=tmp_path, dry_run=False, allow_missing=True
    )

    target = tmp_path / "projects" / "proj-1" / "chips" / "chip-1"
    execution_target = target / "executions" / "20260102" / "001"
    assert (execution_target / "result.json").read_text() == "result"
    assert (target / "shared" / "classifier" / "model.json").read_text() == "bob-new"
    assert (
        target / "shared" / ".migration_conflicts" / "alice" / "model.json"
    ).read_text() == "alice-old"
    assert stats["copied"] == 2
    assert stats["database_records_updated"] == 3
    assert execution_source.exists()

    execution = init_db["execution_history"].find_one({"_id": execution_id})
    assert execution["calib_data_path"] == str(execution_target)
    task = init_db["task_result_history"].find_one({"_id": task_id})
    assert task["figure_path"] == [str(execution_target / "fig" / "result.png")]
    assert task["json_figure_path"] == [str(execution_target / "fig" / "result.json")]
    assert task["raw_data_path"] == [str(execution_target / "raw_data" / "result.nc")]
    knowledge = init_db["issue_knowledge"].find_one({"_id": knowledge_id})
    assert knowledge["figure_paths"] == [str(execution_target / "fig" / "result.png")]
    assert (
        init_db["migration_archive"].count_documents(
            {"migration_id": MIGRATION_ID, "migration_kind": "artifact_path_rewrite"}
        )
        == 3
    )

    repeated = migrate_calibration_files(
        init_db, base_path=tmp_path, dry_run=False, allow_missing=True
    )
    assert repeated["database_records_updated"] == 0
    assert (
        init_db["migration_archive"].count_documents(
            {"migration_id": MIGRATION_ID, "migration_kind": "artifact_path_rewrite"}
        )
        == 3
    )


def test_file_migration_moves_flat_project_execution_to_date_layout(init_db, tmp_path) -> None:
    flat_source = (
        tmp_path / "projects" / "proj-1" / "chips" / "chip-1" / "executions" / "20260102-001"
    )
    flat_source.mkdir(parents=True)
    (flat_source / "result.json").write_text("result")
    execution_id = (
        init_db["execution_history"]
        .insert_one(
            {
                "project_id": "proj-1",
                "chip_id": "chip-1",
                "execution_id": "20260102-001",
                "username": "alice",
                "calib_data_path": str(flat_source),
            }
        )
        .inserted_id
    )

    stats = migrate_calibration_files(init_db, base_path=tmp_path, dry_run=False)

    date_target = flat_source.parent / "20260102" / "001"
    assert (date_target / "result.json").read_text() == "result"
    assert not flat_source.exists()
    assert init_db["execution_history"].find_one({"_id": execution_id})["calib_data_path"] == str(
        date_target
    )
    assert stats["moved"] == 1
    assert stats["database_records_updated"] == 1
    assert "migration_archive_lookup_idx" in init_db["migration_archive"].index_information()


def test_migration_reclaims_expired_lock(init_db) -> None:
    init_db["migration_lock"].insert_one(
        {
            "_id": MIGRATION_ID,
            "acquired_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        }
    )

    migrate_project_scoped_calibration(init_db, dry_run=False)

    assert init_db["migration_lock"].find_one({"_id": MIGRATION_ID}) is None


def test_migration_rejects_active_lock(init_db) -> None:
    init_db["migration_lock"].insert_one(
        {
            "_id": MIGRATION_ID,
            "acquired_at": datetime.now(timezone.utc),
        }
    )

    with pytest.raises(RuntimeError, match="already running"):
        migrate_project_scoped_calibration(init_db, dry_run=False)


def test_migration_rejects_documents_with_missing_project_scope(init_db) -> None:
    init_db["qubit"].insert_one({"chip_id": "chip-1", "qid": "0", "username": "alice", "data": {}})

    dry_run = migrate_project_scoped_calibration(init_db)
    assert dry_run["invalid_scope_documents"]["qubit"] == 1

    with pytest.raises(RuntimeError, match="missing scope fields"):
        migrate_project_scoped_calibration(init_db, dry_run=False)


def test_migration_backfills_project_scope_from_user_default(init_db) -> None:
    init_db["user"].insert_one(
        {
            "user_id": "user-alice",
            "username": "alice",
            "default_project_id": "proj-1",
        }
    )
    qubit_id = (
        init_db["qubit"]
        .insert_one(
            {
                "chip_id": "chip-1",
                "qid": "0",
                "user_id": "user-alice",
                "username": "alice",
                "data": {},
            }
        )
        .inserted_id
    )

    dry_run = migrate_project_scoped_calibration(init_db)

    assert dry_run["scope_backfill_documents"]["qubit"] == 1
    assert dry_run["invalid_scope_documents"]["qubit"] == 0
    assert "project_id" not in init_db["qubit"].find_one({"_id": qubit_id})

    migrate_project_scoped_calibration(init_db, dry_run=False)

    assert init_db["qubit"].find_one({"_id": qubit_id})["project_id"] == "proj-1"
    archived = init_db["migration_archive"].find_one(
        {
            "migration_id": SCOPE_BACKFILL_MIGRATION_ID,
            "source_collection": "qubit",
            "source_id": qubit_id,
        }
    )
    assert "project_id" not in archived["document"]
    assert archived["backfilled_fields"] == {"project_id": "proj-1"}


def test_migration_backfills_project_scope_from_unique_active_membership(init_db) -> None:
    init_db["project_membership"].insert_one(
        {
            "project_id": "proj-1",
            "user_id": "user-alice",
            "username": "alice",
            "status": "active",
        }
    )
    init_db["execution_counter"].insert_one(
        {
            "date": "20260102",
            "chip_id": "chip-1",
            "user_id": "user-alice",
            "username": "alice",
            "index": 1,
        }
    )

    migrate_project_scoped_calibration(init_db, dry_run=False)

    assert init_db["execution_counter"].find_one({})["project_id"] == "proj-1"


def test_migration_rejects_ambiguous_project_memberships(init_db) -> None:
    init_db["project_membership"].insert_many(
        [
            {
                "project_id": project_id,
                "user_id": "user-alice",
                "username": "alice",
                "status": "active",
            }
            for project_id in ("proj-1", "proj-2")
        ]
    )
    init_db["qubit"].insert_one(
        {
            "chip_id": "chip-1",
            "qid": "0",
            "user_id": "user-alice",
            "username": "alice",
            "data": {},
        }
    )

    dry_run = migrate_project_scoped_calibration(init_db)
    assert dry_run["scope_backfill_documents"]["qubit"] == 0
    assert dry_run["invalid_scope_documents"]["qubit"] == 1

    with pytest.raises(RuntimeError, match="missing scope fields"):
        migrate_project_scoped_calibration(init_db, dry_run=False)


def test_migration_does_not_infer_non_project_scope_fields(init_db) -> None:
    init_db["user"].insert_one(
        {
            "user_id": "user-alice",
            "username": "alice",
            "default_project_id": "proj-1",
        }
    )
    init_db["qubit"].insert_one(
        {
            "chip_id": "chip-1",
            "user_id": "user-alice",
            "username": "alice",
            "data": {},
        }
    )

    dry_run = migrate_project_scoped_calibration(init_db)
    assert dry_run["scope_backfill_documents"]["qubit"] == 0
    assert dry_run["invalid_scope_documents"]["qubit"] == 1

    with pytest.raises(RuntimeError, match="missing scope fields"):
        migrate_project_scoped_calibration(init_db, dry_run=False)


def test_migration_backfills_calibration_note_chip_from_execution(init_db) -> None:
    init_db["execution_history"].insert_one(
        {
            "project_id": "proj-1",
            "execution_id": "20260102-001",
            "chip_id": "chip-1",
        }
    )
    note_id = (
        init_db["calibration_note"]
        .insert_one(
            {
                "project_id": "proj-1",
                "execution_id": "20260102-001",
                "task_id": "task-1",
                "username": "alice",
                "note": {},
            }
        )
        .inserted_id
    )

    dry_run = migrate_project_scoped_calibration(init_db)
    assert dry_run["scope_backfill_documents"]["calibration_note"] == 1
    assert dry_run["invalid_scope_documents"]["calibration_note"] == 0

    migrate_project_scoped_calibration(init_db, dry_run=False)

    assert init_db["calibration_note"].find_one({"_id": note_id})["chip_id"] == "chip-1"
    archived = init_db["migration_archive"].find_one(
        {
            "migration_id": SCOPE_BACKFILL_MIGRATION_ID,
            "source_collection": "calibration_note",
            "source_id": note_id,
        }
    )
    assert archived["backfilled_fields"] == {"chip_id": "chip-1"}


def test_migration_rejects_ambiguous_calibration_note_chip(init_db) -> None:
    init_db["execution_history"].drop_indexes()
    init_db["execution_history"].insert_many(
        [
            {
                "project_id": "proj-1",
                "execution_id": "20260102-001",
                "chip_id": chip_id,
            }
            for chip_id in ("chip-1", "chip-2")
        ]
    )
    init_db["calibration_note"].insert_one(
        {
            "project_id": "proj-1",
            "execution_id": "20260102-001",
            "task_id": "task-1",
            "username": "alice",
            "note": {},
        }
    )

    dry_run = migrate_project_scoped_calibration(init_db)
    assert dry_run["scope_backfill_documents"]["calibration_note"] == 0
    assert dry_run["invalid_scope_documents"]["calibration_note"] == 1

    with pytest.raises(RuntimeError, match="missing scope fields"):
        migrate_project_scoped_calibration(init_db, dry_run=False)


def test_file_migration_reports_missing_execution_artifacts(init_db, tmp_path) -> None:
    init_db["execution_history"].insert_one(
        {
            "project_id": "proj-1",
            "chip_id": "chip-1",
            "execution_id": "20260102-001",
            "username": "alice",
            "calib_data_path": str(tmp_path / "alice" / "20260102" / "001"),
        }
    )

    stats = migrate_calibration_files(init_db, base_path=tmp_path, dry_run=False)

    assert stats["missing"] == 1
    assert stats["missing_artifacts"] == [
        {
            "execution_id": "20260102-001",
            "username": "alice",
            "status": None,
            "calib_data_path": str(tmp_path / "alice" / "20260102" / "001"),
            "reason": "legacy artifact directory not found",
            "checked_paths": [
                str(
                    tmp_path
                    / "projects"
                    / "proj-1"
                    / "chips"
                    / "chip-1"
                    / "executions"
                    / "20260102-001"
                ),
                str(tmp_path / "alice" / "20260102" / "001"),
            ],
        }
    ]
    assert stats["missing_artifacts_reviewed"] is False


def test_environment_migration_records_missing_artifacts_and_skips_rerun(
    init_db, tmp_path, monkeypatch, caplog
) -> None:
    init_db["execution_history"].insert_one(
        {
            "project_id": "proj-1",
            "chip_id": "chip-1",
            "execution_id": "20260102-001",
            "username": "alice",
            "status": "failed",
            "calib_data_path": str(tmp_path / "alice" / "20260102" / "001"),
        }
    )
    monkeypatch.setenv("MONGO_DB_NAME", init_db.name)
    monkeypatch.setenv("CALIB_DATA_PATH", str(tmp_path))
    monkeypatch.setattr(migration_module, "MongoClient", lambda *args, **kwargs: init_db.client)

    with caplog.at_level(logging.WARNING):
        stats = run_from_environment(dry_run=False)

    assert stats["files"]["missing"] == 1
    assert "20260102-001" in caplog.text
    ledger = init_db["migration_ledger"].find_one({"migration_id": ARTIFACT_MIGRATION_ID})
    assert ledger is not None
    assert ledger["status"] == "completed"
    assert ledger["stats"]["missing_artifacts"][0]["execution_id"] == "20260102-001"

    reviewed = run_from_environment(dry_run=False, allow_missing_artifacts=True)

    assert reviewed["files"] == {"already_completed": True}
    reviewed_ledger = init_db["migration_ledger"].find_one({"migration_id": ARTIFACT_MIGRATION_ID})
    assert reviewed_ledger is not None
    assert reviewed_ledger["stats"]["missing_artifacts_reviewed"] is True
    assert "missing_artifacts_reviewed_at" in reviewed_ledger

    repeated = run_from_environment(dry_run=False)

    assert repeated["files"] == {"already_completed": True}
