"""Tests for Slack notification service (chat.postMessage variant)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from slack_sdk.errors import SlackApiError

from qdash.api.services.slack_notification_service import SlackNotificationService
from qdash.config import Settings
from qdash.dbmodel.forum import ForumPostDocument
from qdash.dbmodel.slack_forum_thread import SlackForumThreadDocument


def _settings(
    *,
    enabled: bool = True,
    token: str = "xoxb-test-token",  # noqa: S107
    channel_id: str = "C0TESTCHAN",
) -> Settings:
    """Build test Settings with the given Slack forum notification fields."""
    return Settings.model_construct(
        env="test",
        client_url="http://localhost:3000",
        prefect_api_url="http://localhost:4200/api",
        slack_bot_token=token,
        slack_channel_id="test-channel",
        slack_forum_notification=enabled,
        slack_forum_channel_id=channel_id,
        postgres_data_path="/tmp/postgres",
        mongo_data_path="/tmp/mongo",
        calib_data_path="/tmp/calib",
    )


def _post(**overrides: object) -> ForumPostDocument:
    """Build an unsaved ForumPostDocument with overridable defaults."""
    data = {
        "project_id": "project-1",
        "number": 7,
        "category": "qubit",
        "username": "alice",
        "title": "T1 drift on Q12",
        "content": "@qdash please inspect\nLine one\nLine two\nLine three\nLine four",
        "chip_id": "chip-a",
        "target_type": "qubit",
        "target_id": "Q12",
    }
    data.update(overrides)
    return ForumPostDocument(**data)


def _mock_client(ts: str = "111.222", channel: str = "C0TESTCHAN") -> MagicMock:
    """Return a mock WebClient that simulates a successful chat_postMessage call."""
    client = MagicMock()
    response = MagicMock()
    response.__getitem__ = lambda self, key: ts if key == "ts" else channel
    client.chat_postMessage.return_value = response
    return client


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------


def test_is_enabled_returns_true_when_all_set(init_db) -> None:
    """is_enabled is True when the flag, token, and channel are all configured."""
    service = SlackNotificationService(settings=_settings())
    assert service.is_enabled() is True


def test_is_enabled_returns_false_when_flag_false(init_db) -> None:
    """is_enabled is False when the notification flag is disabled."""
    service = SlackNotificationService(settings=_settings(enabled=False))
    assert service.is_enabled() is False


def test_is_enabled_returns_false_when_token_missing(init_db) -> None:
    """is_enabled is False when the bot token is missing."""
    service = SlackNotificationService(settings=_settings(token=""))
    assert service.is_enabled() is False


def test_is_enabled_returns_false_when_channel_missing(init_db) -> None:
    """is_enabled is False when the forum channel ID is missing."""
    service = SlackNotificationService(settings=_settings(channel_id=""))
    assert service.is_enabled() is False


# ---------------------------------------------------------------------------
# _client
# ---------------------------------------------------------------------------


def test_client_uses_configured_bot_token(init_db) -> None:
    """_client builds a WebClient with the configured bot token."""
    service = SlackNotificationService(settings=_settings())
    client = service._client()
    assert client.token == "xoxb-test-token"  # noqa: S105


# ---------------------------------------------------------------------------
# notify_forum_post
# ---------------------------------------------------------------------------


def test_notify_forum_post_skips_when_disabled(init_db) -> None:
    """notify_forum_post sends nothing when notifications are disabled."""
    service = SlackNotificationService(settings=_settings(enabled=False))
    mock_client = _mock_client()
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=_post(), actor_username="alice")
    mock_client.chat_postMessage.assert_not_called()


def test_notify_forum_post_skips_when_token_missing(init_db) -> None:
    """notify_forum_post sends nothing when the bot token is missing."""
    service = SlackNotificationService(settings=_settings(token=""))
    mock_client = _mock_client()
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=_post(), actor_username="alice")
    mock_client.chat_postMessage.assert_not_called()


def test_notify_forum_post_skips_when_channel_missing(init_db) -> None:
    """notify_forum_post sends nothing when the channel ID is missing."""
    service = SlackNotificationService(settings=_settings(channel_id=""))
    mock_client = _mock_client()
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=_post(), actor_username="alice")
    mock_client.chat_postMessage.assert_not_called()


def test_notify_forum_post_skips_replies(init_db) -> None:
    """notify_forum_post ignores replies and AI-generated posts."""
    service = SlackNotificationService(settings=_settings())
    mock_client = _mock_client()
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=_post(parent_id="root-id"), actor_username="alice")
        service.notify_forum_post(post=_post(is_ai_reply=True), actor_username="qdash")
    mock_client.chat_postMessage.assert_not_called()


def test_notify_forum_post_sends_open_status_color_and_records_ts(init_db) -> None:
    """notify_forum_post uses the open-status color and records the message ts."""
    service = SlackNotificationService(settings=_settings())
    ts = "123456789.000100"
    channel = "C0TESTCHAN"
    mock_client = MagicMock()
    mock_response: dict[str, Any] = {"ts": ts, "channel": channel}
    mock_client.chat_postMessage.return_value = mock_response
    post = _post()

    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=post, actor_username="alice")

    call_kwargs = mock_client.chat_postMessage.call_args.kwargs
    assert call_kwargs["channel"] == "C0TESTCHAN"
    attachments = call_kwargs["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["color"] == "#3a5ccc"
    assert "alice" in str(attachments[0]["blocks"])

    # Check DB record was created
    record = SlackForumThreadDocument.find_by_post_id(str(post.id))
    assert record is not None
    assert record.message_ts == ts
    assert record.channel_id == channel


def test_notify_forum_post_truncates_long_excerpt(init_db) -> None:
    """notify_forum_post truncates long content to an ellipsised excerpt."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ts": "ts.010", "channel": "C0TESTCHAN"}
    post = _post(content="x" * 300)

    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=post, actor_username="alice")

    blocks = mock_client.chat_postMessage.call_args.kwargs["attachments"][0]["blocks"]
    excerpt_text = blocks[2]["text"]["text"]
    assert excerpt_text.endswith("...")
    assert "x" * 300 not in excerpt_text


def test_notify_forum_post_links_title_when_post_has_id(init_db) -> None:
    """notify_forum_post links the title to the post URL when the post has an ID."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ts": "ts.011", "channel": "C0TESTCHAN"}
    post = _post()
    post.insert()

    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=post, actor_username="alice")

    blocks = mock_client.chat_postMessage.call_args.kwargs["attachments"][0]["blocks"]
    assert f"http://localhost:3000/forum/{post.id}" in blocks[0]["text"]["text"]


def test_notify_forum_post_shows_dash_when_target_missing(init_db) -> None:
    """notify_forum_post renders "-" for the target field when no target is set."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ts": "ts.012", "channel": "C0TESTCHAN"}
    post = _post(target_type=None, target_id=None)

    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=post, actor_username="alice")

    blocks = mock_client.chat_postMessage.call_args.kwargs["attachments"][0]["blocks"]
    target_field = next(f["text"] for f in blocks[1]["fields"] if f["text"].startswith("*Target:*"))
    assert target_field == "*Target:*\n-"


def test_notify_forum_post_swallows_slack_api_error(init_db) -> None:
    """notify_forum_post logs and swallows SlackApiError."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = SlackApiError(
        "channel_not_found",
        {"error": "channel_not_found"},
    )
    with patch.object(service, "_client", return_value=mock_client):
        # Must not raise
        service.notify_forum_post(post=_post(), actor_username="alice")


def test_notify_forum_post_swallows_generic_exception(init_db) -> None:
    """notify_forum_post logs and swallows unexpected exceptions."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = RuntimeError("network down")
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_post(post=_post(), actor_username="alice")


# ---------------------------------------------------------------------------
# notify_forum_reply
# ---------------------------------------------------------------------------


def test_notify_forum_reply_skips_when_no_thread_record(init_db) -> None:
    """notify_forum_reply sends nothing when no Slack thread record exists."""
    service = SlackNotificationService(settings=_settings())
    mock_client = _mock_client()
    reply = _post(parent_id="nonexistent-root")
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_reply(
            reply_post=reply,
            root_post_id="nonexistent-root",
            actor_username="bob",
        )
    mock_client.chat_postMessage.assert_not_called()


def test_notify_forum_reply_sends_threaded_message_when_record_exists(init_db) -> None:
    # First, create a thread record
    """notify_forum_reply posts into the recorded Slack thread."""
    root = _post()
    root.insert()
    SlackForumThreadDocument.record(
        post_id=str(root.id),
        project_id="project-1",
        channel_id="C0ROOTCHAN",
        message_ts="root.ts.000",
    )

    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ts": "reply.ts", "channel": "C0ROOTCHAN"}
    reply = _post(parent_id=str(root.id), content="My reply content")

    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_reply(
            reply_post=reply,
            root_post_id=str(root.id),
            actor_username="bob",
        )

    call_kwargs = mock_client.chat_postMessage.call_args.kwargs
    assert call_kwargs["channel"] == "C0ROOTCHAN"
    assert call_kwargs["thread_ts"] == "root.ts.000"
    assert "bob" in str(call_kwargs)


def test_notify_forum_reply_skips_when_disabled(init_db) -> None:
    """notify_forum_reply sends nothing when notifications are disabled."""
    service = SlackNotificationService(settings=_settings(enabled=False))
    mock_client = _mock_client()
    reply = _post(parent_id="some-root-id")
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_reply(
            reply_post=reply,
            root_post_id="some-root-id",
            actor_username="bob",
        )
    mock_client.chat_postMessage.assert_not_called()


def test_notify_forum_reply_swallows_exceptions(init_db) -> None:
    # Create thread record
    """notify_forum_reply logs and swallows exceptions."""
    root = _post()
    root.insert()
    SlackForumThreadDocument.record(
        post_id=str(root.id),
        project_id="project-1",
        channel_id="C0ROOTCHAN",
        message_ts="root.ts.000",
    )

    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = RuntimeError("boom")
    reply = _post(parent_id=str(root.id))
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_reply(
            reply_post=reply,
            root_post_id=str(root.id),
            actor_username="bob",
        )


# ---------------------------------------------------------------------------
# notify_forum_status_change
# ---------------------------------------------------------------------------


def test_notify_forum_status_change_resolved_uses_forum_success_color(init_db) -> None:
    """notify_forum_status_change uses the resolved-status color for resolved."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ts": "ts.001", "channel": "C0TESTCHAN"}
    post = _post()

    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_status_change(post=post, actor_username="alice", status="resolved")

    call_kwargs = mock_client.chat_postMessage.call_args.kwargs
    assert call_kwargs["attachments"][0]["color"] == "#18794e"
    assert "Resolved" in str(call_kwargs["attachments"][0]["blocks"])
    assert "thread_ts" not in call_kwargs  # top-level message, no thread


def test_notify_forum_status_change_open_uses_forum_info_color(init_db) -> None:
    """notify_forum_status_change uses the open-status color for open."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.return_value = {"ts": "ts.002", "channel": "C0TESTCHAN"}
    post = _post()

    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_status_change(post=post, actor_username="alice", status="open")

    call_kwargs = mock_client.chat_postMessage.call_args.kwargs
    assert call_kwargs["attachments"][0]["color"] == "#3a5ccc"
    assert "Open" in str(call_kwargs["attachments"][0]["blocks"])


def test_notify_forum_status_change_skips_when_disabled(init_db) -> None:
    """notify_forum_status_change sends nothing when notifications are disabled."""
    service = SlackNotificationService(settings=_settings(enabled=False))
    mock_client = _mock_client()
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_status_change(post=_post(), actor_username="alice", status="resolved")
    mock_client.chat_postMessage.assert_not_called()


def test_notify_forum_status_change_swallows_exceptions(init_db) -> None:
    """notify_forum_status_change logs and swallows exceptions."""
    service = SlackNotificationService(settings=_settings())
    mock_client = MagicMock()
    mock_client.chat_postMessage.side_effect = RuntimeError("oops")
    with patch.object(service, "_client", return_value=mock_client):
        service.notify_forum_status_change(post=_post(), actor_username="alice", status="resolved")
