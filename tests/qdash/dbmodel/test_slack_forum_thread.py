"""Tests for SlackForumThreadDocument upsert behavior."""

from __future__ import annotations

from qdash.dbmodel.slack_forum_thread import SlackForumThreadDocument


def test_record_persists_system_info_on_insert(init_db) -> None:
    """record() persists system_info timestamps to the database on insert."""
    SlackForumThreadDocument.record(
        post_id="post-1",
        project_id="project-1",
        channel_id="C0CHAN",
        message_ts="111.222",
    )

    raw = init_db["slack_forum_thread"].find_one({"post_id": "post-1"})
    assert raw is not None
    assert raw["system_info"]["created_at"] is not None
    assert raw["system_info"]["updated_at"] is not None


def test_record_upsert_updates_message_and_preserves_created_at(init_db) -> None:
    """record() updates message_ts on upsert while preserving created_at."""
    first = SlackForumThreadDocument.record(
        post_id="post-1",
        project_id="project-1",
        channel_id="C0CHAN",
        message_ts="111.222",
    )
    second = SlackForumThreadDocument.record(
        post_id="post-1",
        project_id="project-1",
        channel_id="C0CHAN",
        message_ts="333.444",
    )

    assert second.id == first.id
    assert second.message_ts == "333.444"
    assert second.system_info.created_at == first.system_info.created_at
    assert second.system_info.updated_at >= first.system_info.updated_at
