"""Slack messages for agent interventions, sent with the QDash bot to a separate channel.

The forum notifications in ``slack_notification_service.py`` are unaffected: interventions use
their own channel and toggle (``SLACK_AGENT_NOTIFICATION``, ``SLACK_AGENT_CHANNEL_ID``) and the
same ``SLACK_BOT_TOKEN``. A message carries the project, chip, targets, reason, and a short
question with a link to the QDash intervention page; it never carries log output or the
expert's guidance. The QDash record stays authoritative whether or not a message is sent.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import quote

from slack_sdk import WebClient

from qdash.config import Settings, get_settings

if TYPE_CHECKING:
    from qdash.dbmodel.agent_session import AgentInterventionDocument

MAX_QUESTION_CHARS = 300

REASON_LABELS: dict[str, str] = {
    "unknown_outcome": "Unknown outcome",
    "recovery_exhausted": "Recovery exhausted",
    "evaluation_failed": "Evaluation failed",
    "platform_error": "Platform or hardware error",
    "policy_limit": "Session limit",
    "agent_request": "Agent request",
}

# Status labels and colours, matching the intervention status badges in the UI
# (ui/src/components/features/agent-session/interventionLabels.ts).
STATUS_STYLES: dict[str, tuple[str, str]] = {
    "open": ("Waiting for an expert", "#d97706"),
    "responding": ("Waiting for an expert", "#d97706"),
    "resume_authorized": ("Resume authorized", "#3a5ccc"),
    "resumed": ("Resumed", "#18794e"),
    "stopped": ("Stopped", "#6b7280"),
    "discarded": ("Discarded", "#6b7280"),
}


class SlackPoster(Protocol):
    """The part of ``slack_sdk.WebClient`` the notifier uses."""

    def chat_postMessage(self, *, channel: str, **kwargs: Any) -> Any:
        """Post a message."""


def _excerpt(value: str, limit: int = MAX_QUESTION_CHARS) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _field(label: str, value: str | None) -> dict[str, str]:
    return {"type": "mrkdwn", "text": f"*{label}:*\n{escape(value or '-', quote=False)}"}


class AgentInterventionSlackNotifier:
    """Post intervention messages to the agent channel; callers record the delivery state."""

    def __init__(self, settings: Settings | None = None, client: SlackPoster | None = None) -> None:
        """Initialize with application settings and an optional Slack client for tests."""
        self._settings = settings or get_settings()
        self._client_override = client

    def _client(self) -> SlackPoster:
        if self._client_override is not None:
            return self._client_override
        return WebClient(token=self._settings.slack_bot_token, timeout=5)

    def is_enabled(self) -> bool:
        """Return whether agent intervention messages should be sent."""
        return bool(
            self._settings.slack_agent_notification
            and self._settings.slack_bot_token
            and self._settings.slack_agent_channel_id
        )

    def intervention_url(self, doc: AgentInterventionDocument) -> str:
        """The QDash page of the intervention, with the project selected."""
        base = self._settings.public_url.rstrip("/")
        return (
            f"{base}/agent-sessions/{quote(doc.session_id, safe='')}"
            f"/interventions/{quote(doc.intervention_id, safe='')}"
            f"?project={quote(doc.project_id, safe='')}"
        )

    def post_root(self, doc: AgentInterventionDocument, *, project_name: str) -> tuple[str, str]:
        """Post the root message and return its channel and timestamp. Raises on failure."""
        reason = REASON_LABELS.get(doc.reason.value, doc.reason.value)
        label, color = STATUS_STYLES.get(doc.status.value, (doc.status.value, "#9ca3af"))
        url = escape(self.intervention_url(doc), quote=False)
        title = f"Agent needs an expert: {reason}"
        targets = ", ".join(doc.qids) if doc.qids else None
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*<{url}|{title}>*"}},
            {
                "type": "section",
                "fields": [
                    _field("Project", project_name),
                    _field("Environment", self._settings.env),
                    _field("Chip", doc.chip_id),
                    _field("Targets", targets),
                    _field("Task", doc.task_name),
                    _field("Status", label),
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Question:*\n{escape(_excerpt(doc.question) or '-', quote=False)}",
                },
            },
        ]
        response = self._client().chat_postMessage(
            channel=self._settings.slack_agent_channel_id,
            text=escape(f"{title} ({doc.chip_id} {targets or ''})".strip(), quote=False),
            attachments=[{"color": color, "blocks": blocks}],
            unfurl_links=False,
        )
        return str(response["channel"]), str(response["ts"])

    def post_reply(self, doc: AgentInterventionDocument, text: str) -> None:
        """Reply in the intervention's thread. Raises on failure."""
        if not doc.notification.channel_id or not doc.notification.message_ts:
            return
        url = escape(self.intervention_url(doc), quote=False)
        self._client().chat_postMessage(
            channel=doc.notification.channel_id,
            thread_ts=doc.notification.message_ts,
            text=f"{escape(text, quote=False)} <{url}|Open in QDash>",
            unfurl_links=False,
        )
