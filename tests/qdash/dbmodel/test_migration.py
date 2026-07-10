from typing import cast

import pytest
from pymongo.errors import DuplicateKeyError

from qdash.dbmodel.forum import ForumCounterDocument, ForumPostDocument
from qdash.dbmodel.migration import (
    MigrationError,
    migrate_backfill_forum_thread_numbers,
    migrate_forum_status,
)


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
