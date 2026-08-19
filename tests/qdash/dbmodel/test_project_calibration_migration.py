import os
from datetime import datetime, timezone

import pytest

from qdash.dbmodel.project_calibration_migration import (
    MIGRATION_ID,
    migrate_calibration_files,
    migrate_project_scoped_calibration,
)


def test_migration_archives_duplicates_and_installs_project_indexes(init_db) -> None:
    qubits = init_db["qubit"]
    counters = init_db["execution_counter"]
    notes = init_db["calibration_note"]
    qubits.drop_indexes()
    counters.drop_indexes()
    notes.drop_indexes()
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
    assert "project_id_1_date_1_chip_id_1" in counters.index_information()
    ledger = init_db["migration_ledger"].find_one({"migration_id": MIGRATION_ID})
    assert ledger["status"] == "completed"
    repeated = migrate_project_scoped_calibration(init_db, dry_run=False)
    assert repeated["already_completed"] is True


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
    assert (target / "executions" / "20260102-001" / "result.json").read_text() == "result"
    assert (target / "shared" / "classifier" / "model.json").read_text() == "bob-new"
    assert (
        target / "shared" / ".migration_conflicts" / "alice" / "model.json"
    ).read_text() == "alice-old"
    assert stats["copied"] == 2
    assert stats["database_records_updated"] == 3
    assert execution_source.exists()

    execution = init_db["execution_history"].find_one({"_id": execution_id})
    assert execution["calib_data_path"] == str(target / "executions" / "20260102-001")
    task = init_db["task_result_history"].find_one({"_id": task_id})
    assert task["figure_path"] == [
        str(target / "executions" / "20260102-001" / "fig" / "result.png")
    ]
    assert task["json_figure_path"] == [
        str(target / "executions" / "20260102-001" / "fig" / "result.json")
    ]
    assert task["raw_data_path"] == [
        str(target / "executions" / "20260102-001" / "raw_data" / "result.nc")
    ]
    knowledge = init_db["issue_knowledge"].find_one({"_id": knowledge_id})
    assert knowledge["figure_paths"] == [
        str(target / "executions" / "20260102-001" / "fig" / "result.png")
    ]
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


def test_file_migration_rejects_missing_execution_artifacts(init_db, tmp_path) -> None:
    init_db["execution_history"].insert_one(
        {
            "project_id": "proj-1",
            "chip_id": "chip-1",
            "execution_id": "20260102-001",
            "username": "alice",
            "calib_data_path": str(tmp_path / "alice" / "20260102" / "001"),
        }
    )

    with pytest.raises(RuntimeError, match="allow-missing-artifacts"):
        migrate_calibration_files(init_db, base_path=tmp_path, dry_run=False)
