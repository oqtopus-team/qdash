"""Tests for ForumService Slack notification integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.api.services.forum_service import ForumService

if TYPE_CHECKING:
    from qdash.dbmodel.forum import ForumPostDocument


class _SlackRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def notify_forum_post(self, *, post: ForumPostDocument, actor_username: str) -> None:
        self.calls.append({"post": post, "actor_username": actor_username})


def test_create_post_notifies_slack_for_root_threads_only(init_db) -> None:
    slack = _SlackRecorder()
    service = ForumService(slack_notification_service=slack)

    root = service.create_post(
        project_id="project-1",
        username="alice",
        category="qubit",
        title="T1 drift",
        content="Root content",
        parent_id=None,
    )
    service.create_post(
        project_id="project-1",
        username="bob",
        category="qubit",
        title=None,
        content="Reply content",
        parent_id=root.id,
    )

    assert len(slack.calls) == 1
    assert slack.calls[0]["actor_username"] == "alice"
    assert slack.calls[0]["post"].parent_id is None


def test_create_ai_reply_does_not_notify_slack(init_db) -> None:
    slack = _SlackRecorder()
    service = ForumService(slack_notification_service=slack)

    root = service.create_post(
        project_id="project-1",
        username="alice",
        category="qubit",
        title="T1 drift",
        content="Root content",
        parent_id=None,
    )
    slack.calls.clear()

    service.save_ai_reply(
        project_id="project-1",
        parent_id=root.id,
        content="AI reply",
    )

    assert slack.calls == []
