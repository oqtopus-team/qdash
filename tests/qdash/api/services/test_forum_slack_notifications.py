"""Tests for ForumService Slack notification integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from qdash.api.services.forum_service import ForumService

if TYPE_CHECKING:
    from qdash.api.services.slack_notification_service import SlackNotificationService
    from qdash.dbmodel.forum import ForumPostDocument


class _SlackRecorder:
    def __init__(self) -> None:
        self.post_calls: list[dict[str, Any]] = []
        self.reply_calls: list[dict[str, Any]] = []
        self.status_calls: list[dict[str, Any]] = []

    def notify_forum_post(self, *, post: ForumPostDocument, actor_username: str) -> None:
        self.post_calls.append({"post": post, "actor_username": actor_username})

    def notify_forum_reply(
        self,
        *,
        reply_post: ForumPostDocument,
        root_post_id: str,
        actor_username: str,
    ) -> None:
        self.reply_calls.append(
            {
                "reply_post": reply_post,
                "root_post_id": root_post_id,
                "actor_username": actor_username,
            }
        )

    def notify_forum_status_change(
        self,
        *,
        post: ForumPostDocument,
        actor_username: str,
        status: str,
    ) -> None:
        self.status_calls.append({"post": post, "actor_username": actor_username, "status": status})


def test_create_root_post_notifies_slack(init_db) -> None:
    slack = _SlackRecorder()
    service = ForumService(slack_notification_service=cast("SlackNotificationService", slack))

    service.create_post(
        project_id="project-1",
        username="alice",
        category="qubit",
        title="T1 drift",
        content="Root content",
        parent_id=None,
    )

    assert len(slack.post_calls) == 1
    assert slack.post_calls[0]["actor_username"] == "alice"
    assert slack.post_calls[0]["post"].parent_id is None


def test_create_reply_notifies_slack_reply(init_db) -> None:
    slack = _SlackRecorder()
    service = ForumService(slack_notification_service=cast("SlackNotificationService", slack))

    root = service.create_post(
        project_id="project-1",
        username="alice",
        category="qubit",
        title="T1 drift",
        content="Root content",
        parent_id=None,
    )
    slack.post_calls.clear()

    service.create_post(
        project_id="project-1",
        username="bob",
        category="qubit",
        title=None,
        content="Reply content",
        parent_id=root.id,
    )

    assert slack.post_calls == []
    assert len(slack.reply_calls) == 1
    assert slack.reply_calls[0]["actor_username"] == "bob"
    assert slack.reply_calls[0]["root_post_id"] == root.id


def test_create_post_no_slack_notification_when_no_service(init_db) -> None:
    """ForumService without slack_notification_service must not raise."""
    service = ForumService(slack_notification_service=None)

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
        content="Reply",
        parent_id=root.id,
    )


def test_save_ai_reply_notifies_slack_reply(init_db) -> None:
    slack = _SlackRecorder()
    service = ForumService(slack_notification_service=cast("SlackNotificationService", slack))

    root = service.create_post(
        project_id="project-1",
        username="alice",
        category="qubit",
        title="T1 drift",
        content="Root content",
        parent_id=None,
    )
    slack.post_calls.clear()

    service.save_ai_reply(
        project_id="project-1",
        parent_id=root.id,
        content="AI reply content",
    )

    assert len(slack.reply_calls) == 1
    assert slack.reply_calls[0]["actor_username"] == "qdash"
    assert slack.reply_calls[0]["root_post_id"] == root.id


def test_close_post_notifies_slack_status_change(init_db) -> None:
    from qdash.datamodel.project import ProjectRole

    slack = _SlackRecorder()
    service = ForumService(slack_notification_service=cast("SlackNotificationService", slack))

    root = service.create_post(
        project_id="project-1",
        username="alice",
        category="qubit",
        title="T1 drift",
        content="Root content",
        parent_id=None,
    )
    slack.post_calls.clear()

    service.close_post(
        project_id="project-1",
        post_id=root.id,
        username="alice",
        role=ProjectRole.OWNER,
    )

    assert len(slack.status_calls) == 1
    assert slack.status_calls[0]["status"] == "closed"
    assert slack.status_calls[0]["actor_username"] == "alice"


def test_reopen_post_notifies_slack_status_change(init_db) -> None:
    from qdash.datamodel.project import ProjectRole

    slack = _SlackRecorder()
    service = ForumService(slack_notification_service=cast("SlackNotificationService", slack))

    root = service.create_post(
        project_id="project-1",
        username="alice",
        category="qubit",
        title="T1 drift",
        content="Root content",
        parent_id=None,
    )
    service.close_post(
        project_id="project-1",
        post_id=root.id,
        username="alice",
        role=ProjectRole.OWNER,
    )
    slack.status_calls.clear()

    service.reopen_post(
        project_id="project-1",
        post_id=root.id,
        username="alice",
        role=ProjectRole.OWNER,
    )

    assert len(slack.status_calls) == 1
    assert slack.status_calls[0]["status"] == "open"
    assert slack.status_calls[0]["actor_username"] == "alice"
