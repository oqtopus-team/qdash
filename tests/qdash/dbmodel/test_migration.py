from typing import cast

import pytest
from pymongo.errors import DuplicateKeyError

from qdash.dbmodel.forum import ForumCounterDocument, ForumPostDocument
from qdash.dbmodel.migration import (
    RENAME_AGENT_CANDIDATE_SET_COMMITS_MIGRATION_ID,
    RENAME_CHECK_CHEVRON_MIGRATION_ID,
    RENAME_CHECK_EF_CHEVRON_MIGRATION_ID,
    MigrationError,
    migrate_backfill_forum_thread_numbers,
    migrate_forum_status,
    migrate_rename_agent_candidate_set_commits,
    migrate_rename_check_chevron,
    migrate_rename_check_ef_chevron,
    run_pending_database_migrations,
)


def test_rename_check_chevron_migration_uses_ledger_and_preserves_task_catalog(init_db):
    history_fields = {
        "task_result_history": "name",
        "parameter_versions": "task_name",
        "provenance_activities": "task_name",
        "issue_knowledge": "task_name",
        "agent_candidate_commits": "task_name",
        "agent_actions": "task_name",
    }
    for collection_name, field_name in history_fields.items():
        init_db[collection_name].insert_one({field_name: "CheckChevron"})
    init_db["note_event"].insert_one({"extra": {"task_name": "CheckChevron"}})
    init_db["task"].insert_one({"name": "CheckChevron"})

    dry_run = migrate_rename_check_chevron(init_db)

    assert dry_run["matched"] == len(history_fields) + 1
    assert dry_run["updated"] == 0
    assert init_db["task_result_history"].find_one()["name"] == "CheckChevron"
    assert init_db["migration_ledger"].count_documents({}) == 0

    executed = run_pending_database_migrations(init_db, dry_run=False)

    result = executed[RENAME_CHECK_CHEVRON_MIGRATION_ID]
    assert result["already_completed"] is False
    assert result["stats"]["matched"] == len(history_fields) + 1
    assert result["stats"]["updated"] == len(history_fields) + 1
    for collection_name, field_name in history_fields.items():
        assert init_db[collection_name].find_one()[field_name] == "CheckAdaptiveChevron"
    assert init_db["note_event"].find_one()["extra"]["task_name"] == "CheckAdaptiveChevron"
    assert init_db["task"].find_one()["name"] == "CheckChevron"
    ledger = init_db["migration_ledger"].find_one(
        {"migration_id": RENAME_CHECK_CHEVRON_MIGRATION_ID}
    )
    assert ledger["status"] == "completed"

    repeated = run_pending_database_migrations(init_db, dry_run=False)

    assert repeated[RENAME_CHECK_CHEVRON_MIGRATION_ID]["already_completed"] is True


def test_rename_check_ef_chevron_migration_uses_ledger_and_preserves_task_catalog(init_db):
    history_fields = {
        "task_result_history": "name",
        "parameter_versions": "task_name",
        "provenance_activities": "task_name",
        "issue_knowledge": "task_name",
        "agent_candidate_commits": "task_name",
        "agent_actions": "task_name",
    }
    for collection_name, field_name in history_fields.items():
        init_db[collection_name].insert_one({field_name: "CheckEFChevron"})
    init_db["note_event"].insert_one({"extra": {"task_name": "CheckEFChevron"}})
    init_db["task"].insert_one({"name": "CheckEFChevron"})

    dry_run = migrate_rename_check_ef_chevron(init_db)

    assert dry_run["matched"] == len(history_fields) + 1
    assert dry_run["updated"] == 0
    assert init_db["task_result_history"].find_one()["name"] == "CheckEFChevron"
    assert init_db["migration_ledger"].count_documents({}) == 0

    executed = run_pending_database_migrations(init_db, dry_run=False)

    result = executed[RENAME_CHECK_EF_CHEVRON_MIGRATION_ID]
    assert result["already_completed"] is False
    assert result["stats"]["matched"] == len(history_fields) + 1
    assert result["stats"]["updated"] == len(history_fields) + 1
    for collection_name, field_name in history_fields.items():
        assert init_db[collection_name].find_one()[field_name] == "CheckAdaptiveEFChevron"
    assert init_db["note_event"].find_one()["extra"]["task_name"] == ("CheckAdaptiveEFChevron")
    assert init_db["task"].find_one()["name"] == "CheckEFChevron"
    ledger = init_db["migration_ledger"].find_one(
        {"migration_id": RENAME_CHECK_EF_CHEVRON_MIGRATION_ID}
    )
    assert ledger["status"] == "completed"

    repeated = run_pending_database_migrations(init_db, dry_run=False)

    assert repeated[RENAME_CHECK_EF_CHEVRON_MIGRATION_ID]["already_completed"] is True


def test_rename_agent_candidate_set_commits_moves_the_collection(init_db):
    init_db["agent_campaign_commits"].insert_many(
        [{"_id": "c1", "commit_id": "c1"}, {"_id": "c2", "commit_id": "c2"}]
    )

    dry_run = migrate_rename_agent_candidate_set_commits(init_db)

    assert dry_run == {"matched": 2, "moved": 0, "renamed": False}
    assert init_db["agent_candidate_set_commits"].count_documents({}) == 0

    executed = run_pending_database_migrations(init_db, dry_run=False)

    result = executed[RENAME_AGENT_CANDIDATE_SET_COMMITS_MIGRATION_ID]
    assert result["stats"] == {"matched": 2, "moved": 2, "renamed": True}
    assert "agent_campaign_commits" not in init_db.list_collection_names()
    assert init_db["agent_candidate_set_commits"].count_documents({}) == 2
    assert run_pending_database_migrations(init_db, dry_run=False)[
        RENAME_AGENT_CANDIDATE_SET_COMMITS_MIGRATION_ID
    ]["already_completed"]


def test_rename_agent_candidate_set_commits_merges_into_an_existing_collection(init_db):
    def commit(commit_id: str) -> dict[str, str]:
        return {
            "_id": commit_id,
            "commit_id": commit_id,
            "project_id": "p",
            "session_id": "s",
            "idempotency_key": f"key-{commit_id}",
        }

    init_db["agent_campaign_commits"].insert_many([commit("c1"), commit("c2")])
    init_db["agent_candidate_set_commits"].insert_one(commit("c2"))

    stats = migrate_rename_agent_candidate_set_commits(init_db, dry_run=False)

    assert stats == {"matched": 2, "moved": 1, "renamed": False}
    assert "agent_campaign_commits" not in init_db.list_collection_names()
    assert sorted(d["_id"] for d in init_db["agent_candidate_set_commits"].find()) == ["c1", "c2"]


def test_rename_agent_candidate_set_commits_without_the_old_collection_is_a_no_op(init_db):
    assert migrate_rename_agent_candidate_set_commits(init_db, dry_run=False) == {
        "matched": 0,
        "moved": 0,
        "renamed": False,
    }


def _forum_post(post_id) -> ForumPostDocument:
    doc = ForumPostDocument.find_one({"_id": post_id}).run()
    assert doc is not None
    return cast("ForumPostDocument", doc)


def _forum_counter(project_id: str) -> ForumCounterDocument:
    doc = ForumCounterDocument.find_one({"project_id": project_id}).run()
    assert doc is not None
    return cast("ForumCounterDocument", doc)


def test_backfill_forum_thread_numbers_assigns_roots_replies_and_counter(init_db):
    existing = ForumPostDocument(
        project_id="project-a",
        number=3,
        category="qubit",
        username="owner",
        title="Existing numbered thread",
        content="root",
    ).insert()
    missing = ForumPostDocument(
        project_id="project-a",
        category="qubit",
        username="owner",
        title="Missing numbered thread",
        content="root",
    ).insert()
    reply = ForumPostDocument(
        project_id="project-a",
        category="qubit",
        username="owner",
        content="reply",
        parent_id=str(missing.id),
    ).insert()
    orphan = ForumPostDocument(
        project_id="project-a",
        category="qubit",
        username="owner",
        content="orphan",
        parent_id="missing-root",
    ).insert()
    ForumCounterDocument(project_id="project-a", value=10).insert()

    dry_run = migrate_backfill_forum_thread_numbers()

    assert dry_run["root_threads_missing_number"] == 1
    assert dry_run["root_threads_updated"] == 0
    assert dry_run["replies_updated"] == 1
    assert dry_run["orphan_replies_found"] == 1
    assert dry_run["projects"][0]["counter_value"] == 10
    assert _forum_post(existing.id).number == 3
    assert _forum_post(missing.id).number is None
    assert _forum_post(reply.id).number is None
    assert _forum_post(orphan.id).number is None

    executed = migrate_backfill_forum_thread_numbers(dry_run=False)

    assert executed["root_threads_updated"] == 1
    assert executed["replies_updated"] == 1
    assert _forum_post(existing.id).number == 3
    assert _forum_post(missing.id).number == 1
    assert _forum_post(reply.id).number == 1
    assert _forum_post(orphan.id).number is None
    assert _forum_counter("project-a").value == 10

    repeated = migrate_backfill_forum_thread_numbers(dry_run=False)

    assert repeated["root_threads_updated"] == 0
    assert repeated["replies_updated"] == 0


def test_backfill_forum_thread_numbers_blocks_duplicate_existing_root_numbers(init_db):
    first = ForumPostDocument(
        project_id="project-a",
        number=1,
        category="qubit",
        username="owner",
        title="First",
        content="root",
    )
    first.insert()
    second = ForumPostDocument(
        project_id="project-a",
        number=1,
        category="qubit",
        username="owner",
        title="Second",
        content="root",
    )
    try:
        second.insert()
    except DuplicateKeyError:
        ForumPostDocument.get_motor_collection().insert_one(second.model_dump(by_alias=True))

    dry_run = migrate_backfill_forum_thread_numbers()

    assert dry_run["duplicate_root_numbers"] == {
        "project-a": {"1": [str(first.id), str(second.id)]}
    }

    with pytest.raises(MigrationError):
        migrate_backfill_forum_thread_numbers(dry_run=False)


def test_migrate_forum_status_moves_closed_and_legacy_labels(init_db):
    closed = ForumPostDocument(
        project_id="project-a",
        category="qubit",
        username="owner",
        title="Closed old thread",
        content="root",
        labels=["resolved"],
    ).insert()
    review = ForumPostDocument(
        project_id="project-a",
        category="qubit",
        username="owner",
        title="Weekly discussion",
        content="root",
        labels=["discussion"],
    ).insert()
    plain = ForumPostDocument(
        project_id="project-a",
        category="qubit",
        username="owner",
        title="Plain thread",
        content="root",
    ).insert()
    collection = ForumPostDocument.get_motor_collection()
    collection.update_one({"_id": closed.id}, {"$set": {"is_closed": True}})
    collection.update_one({"_id": plain.id}, {"$unset": {"status": ""}})

    dry_run = migrate_forum_status()

    assert dry_run["posts_to_update"] == 3
    assert dry_run["status_from_resolved_label"] == 1
    assert dry_run["labels_changed"] == 2
    dry_run_closed_doc = collection.find_one({"_id": closed.id})
    assert dry_run_closed_doc is not None
    assert dry_run_closed_doc.get("is_closed") is True

    executed = migrate_forum_status(dry_run=False)

    assert executed["posts_to_update"] == 3
    closed_doc = collection.find_one({"_id": closed.id})
    review_doc = collection.find_one({"_id": review.id})
    plain_doc = collection.find_one({"_id": plain.id})
    assert closed_doc is not None
    assert review_doc is not None
    assert plain_doc is not None
    assert closed_doc["status"] == "resolved"
    assert closed_doc["labels"] == []
    assert "is_closed" not in closed_doc
    assert review_doc["labels"] == ["review"]
    assert plain_doc["status"] == "open"


def test_backfill_task_result_system_id_copies_the_chip(init_db):
    from qdash.dbmodel.migration import (
        BACKFILL_TASK_RESULT_SYSTEM_ID_MIGRATION_ID,
        migrate_backfill_task_result_system_id,
    )

    init_db["task_result_history"].insert_many(
        [
            {"task_id": "a", "chip_id": "64Qv3"},
            {"task_id": "b", "chip_id": "144Qv3", "system_id": None},
            {"task_id": "c", "chip_id": "144Qv3", "system_id": "144Qv3-quel3"},
        ]
    )

    assert migrate_backfill_task_result_system_id(init_db) == {"matched": 2, "updated": 0}
    assert init_db["task_result_history"].find_one({"task_id": "a"}).get("system_id") is None

    executed = run_pending_database_migrations(init_db, dry_run=False)

    assert executed[BACKFILL_TASK_RESULT_SYSTEM_ID_MIGRATION_ID]["stats"]["updated"] == 2
    by_task = {doc["task_id"]: doc["system_id"] for doc in init_db["task_result_history"].find()}
    assert by_task == {"a": "64Qv3", "b": "144Qv3", "c": "144Qv3-quel3"}


def test_create_chip_calibration_note_master_copies_the_newest_snapshot(init_db):
    from qdash.dbmodel.migration import (
        CHIP_CALIBRATION_NOTE_MASTER_MIGRATION_ID,
        migrate_create_chip_calibration_note_master,
    )

    init_db["calibration_note"].insert_many(
        [
            {
                "project_id": "p",
                "chip_id": "a",
                "task_id": "master",
                "execution_id": "e1",
                "timestamp": "2026-01-01T00:00:00",
                "note": {"v": 1},
                "version": 3,
            },
            {
                "project_id": "p",
                "chip_id": "a",
                "task_id": "master",
                "execution_id": "e2",
                "timestamp": "2026-01-02T00:00:00",
                "note": {"v": 2},
                "version": 1,
            },
            {
                "project_id": "p",
                "chip_id": "b",
                "task_id": "master",
                "execution_id": "master",
                "timestamp": "2026-01-01T00:00:00",
                "note": {"v": 9},
            },
            {
                "project_id": "p",
                "chip_id": "c",
                "task_id": "other",
                "execution_id": "e3",
                "timestamp": "2026-01-01T00:00:00",
                "note": {},
            },
        ]
    )

    assert migrate_create_chip_calibration_note_master(init_db) == {"matched": 1, "created": 0}

    executed = run_pending_database_migrations(init_db, dry_run=False)

    assert executed[CHIP_CALIBRATION_NOTE_MASTER_MIGRATION_ID]["stats"] == {
        "matched": 1,
        "created": 1,
    }
    created = init_db["calibration_note"].find_one(
        {"chip_id": "a", "execution_id": "master", "task_id": "master"}
    )
    assert created["note"] == {"v": 2}
    assert created["version"] == 0
    assert init_db["calibration_note"].count_documents({"chip_id": "a"}) == 3
    assert init_db["calibration_note"].count_documents({"chip_id": "b"}) == 1
