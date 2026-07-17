"""Slack chat.postMessage notifications for QDash API events."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from slack_sdk import WebClient

from qdash.config import Settings, get_settings
from qdash.dbmodel.slack_forum_thread import SlackForumThreadDocument

if TYPE_CHECKING:
    from qdash.dbmodel.forum import ForumPostDocument

logger = logging.getLogger(__name__)

MAX_EXCERPT_CHARS = 200
MENTION_PATTERN = re.compile(r"@qdash\b", re.IGNORECASE)

# Forum workflow status labels and badge colours; keep in sync with the
# status badges in ui/src/components/features/forum/categories.tsx and the
# light-theme palette in ui/src/app/globals.css.
_STATUS_STYLES: dict[str, tuple[str, str]] = {
    "open": ("Open", "#3a5ccc"),
    "investigating": ("Investigating", "#d97706"),
    "identified": ("Identified", "#e21331"),
    "resolved": ("Resolved", "#18794e"),
}


def _excerpt(content: str, *, limit: int = MAX_EXCERPT_CHARS) -> str:
    """Return a compact Slack-safe excerpt from forum post content."""
    value = MENTION_PATTERN.sub("", content)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    text = "\n".join(lines[:3]).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def _format_field(label: str, value: str | None) -> dict[str, Any]:
    display = value if value else "-"
    return {"type": "mrkdwn", "text": f"*{label}:*\n{display}"}


class SlackNotificationService:
    """Send Slack chat.postMessage notifications for selected API events."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize with application settings."""
        self._settings = settings or get_settings()

    def _client(self) -> WebClient:
        """Return a configured Slack WebClient."""
        return WebClient(token=self._settings.slack_bot_token, timeout=5)

    def is_enabled(self) -> bool:
        """Return whether Slack forum notifications should be sent."""
        return bool(
            self._settings.slack_forum_notification
            and self._settings.slack_bot_token
            and self._settings.slack_forum_channel_id
        )

    def notify_forum_post(self, *, post: ForumPostDocument, actor_username: str) -> None:
        """Send a Slack notification for a newly created root forum thread."""
        if post.parent_id is not None or post.is_ai_reply:
            return
        if not self.is_enabled():
            return

        title = post.title or "Forum thread"
        title_text = f"#{post.number} {title}" if post.number is not None else title
        url = self._forum_post_url(post)
        title_block = f"*<{url}|{title_text}>*" if url else f"*{title_text}*"
        text = f"New forum thread: {title_text}"
        content_excerpt = _excerpt(post.content) or "-"

        fields = [
            _format_field("Author", actor_username),
            _format_field("Environment", self._settings.env),
            _format_field("Chip", post.chip_id),
            _format_field("Target", self._target_label(post)),
            _format_field("Category", post.category),
        ]

        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": title_block}},
            {"type": "section", "fields": fields},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Excerpt:*\n{content_excerpt}"},
            },
        ]

        _, color = _STATUS_STYLES.get(post.status or "open", _STATUS_STYLES["open"])
        try:
            response = self._client().chat_postMessage(
                channel=self._settings.slack_forum_channel_id,
                text=text,
                attachments=[{"color": color, "blocks": blocks}],
            )
            SlackForumThreadDocument.record(
                post_id=str(post.id),
                project_id=post.project_id,
                channel_id=response["channel"],
                message_ts=response["ts"],
            )
        except Exception:
            logger.exception("Failed to send Slack forum notification for post %s", post.id)

    def notify_forum_reply(
        self,
        *,
        reply_post: ForumPostDocument,
        root_post_id: str,
        actor_username: str,
    ) -> None:
        """Send a Slack thread reply notification for a forum reply."""
        if not self.is_enabled():
            return

        thread_record = SlackForumThreadDocument.find_by_post_id(root_post_id)
        if thread_record is None:
            logger.info(
                "No Slack thread record found for root post %s; skipping reply notification",
                root_post_id,
            )
            return

        content_excerpt = _excerpt(reply_post.content) or "-"
        text = f"{actor_username} replied: {content_excerpt}"
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{actor_username}* replied:\n{content_excerpt}",
                },
            },
        ]

        try:
            self._client().chat_postMessage(
                channel=thread_record.channel_id,
                thread_ts=thread_record.message_ts,
                text=text,
                blocks=blocks,
            )
        except Exception:
            logger.exception("Failed to send Slack reply notification for post %s", reply_post.id)

    def notify_forum_status_change(
        self,
        *,
        post: ForumPostDocument,
        actor_username: str,
        status: str,
    ) -> None:
        """Send a Slack notification for a forum thread status change.

        Args:
            post: The forum post document.
            actor_username: The username of the actor changing the status.
            status: New workflow status (open/investigating/identified/resolved).
        """
        if not self.is_enabled():
            return

        title = post.title or "Forum thread"
        title_text = f"#{post.number} {title}" if post.number is not None else title
        url = self._forum_post_url(post)
        title_link = f"<{url}|{title_text}>" if url else title_text

        label, color = _STATUS_STYLES.get(status, (status, "#9ca3af"))

        text = f"Forum thread status changed to {label}: {title_text}"
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Status changed to {label}*\n"
                        f"*Thread:* {title_link}\n"
                        f"*By:* {actor_username}\n"
                        f"*Environment:* {self._settings.env}"
                    ),
                },
            },
        ]

        try:
            self._client().chat_postMessage(
                channel=self._settings.slack_forum_channel_id,
                text=text,
                attachments=[{"color": color, "blocks": blocks}],
            )
        except Exception:
            logger.exception("Failed to send Slack status-change notification for post %s", post.id)

    def _forum_post_url(self, post: ForumPostDocument) -> str:
        base = self._settings.client_url.rstrip("/")
        if not base or post.id is None:
            return ""
        return f"{base}/forum/{post.id}"

    @staticmethod
    def _target_label(post: ForumPostDocument) -> str | None:
        if not (post.target_type and post.target_id):
            return None
        return f"{post.target_type}:{post.target_id}"
