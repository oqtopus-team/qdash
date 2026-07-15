"""Slack webhook notifications for QDash API events."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import httpx

from qdash.config import Settings, get_settings
from qdash.dbmodel.system_setting import SystemSettingDocument

if TYPE_CHECKING:
    from qdash.dbmodel.forum import ForumPostDocument

logger = logging.getLogger(__name__)

MAX_EXCERPT_CHARS = 200
MENTION_PATTERN = re.compile(r"@qdash\b", re.IGNORECASE)


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
    """Send Slack Incoming Webhook notifications for selected API events."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize with application settings."""
        self._settings = settings or get_settings()

    def is_enabled(self) -> bool:
        """Return whether Slack forum notifications should be sent."""
        if not self._settings.slack_webhook_url:
            return False
        system_setting = SystemSettingDocument.get_singleton()
        return system_setting.slack_forum_notifications_enabled

    def notify_forum_post(self, *, post: ForumPostDocument, actor_username: str) -> None:
        """Send a Slack notification for a newly created root forum thread."""
        if post.parent_id is not None or post.is_ai_reply:
            return
        if not self.is_enabled():
            return

        payload = self._build_forum_post_payload(post=post, actor_username=actor_username)
        try:
            response = httpx.post(
                self._settings.slack_webhook_url,
                json=payload,
                timeout=5.0,
            )
            response.raise_for_status()
        except Exception:
            logger.exception("Failed to send Slack forum notification for post %s", post.id)

    def _build_forum_post_payload(
        self, *, post: ForumPostDocument, actor_username: str
    ) -> dict[str, Any]:
        """Build the Slack webhook payload for a forum thread."""
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

        return {
            "text": text,
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": title_block}},
                {"type": "section", "fields": fields},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Excerpt:*\n{content_excerpt}"},
                },
            ],
        }

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
