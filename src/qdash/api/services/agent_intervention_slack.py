"""Slack messages for agent interventions and session lifecycle events, sent with the QDash
bot to a separate channel.

The forum notifications in ``slack_notification_service.py`` are unaffected: interventions use
their own channel and toggle (``SLACK_AGENT_NOTIFICATION``, ``SLACK_AGENT_CHANNEL_ID``) and the
same ``SLACK_BOT_TOKEN``. A message carries the project, chip, targets, reason, and a short
question with a link to the QDash intervention page; it never carries log output or the
expert's guidance. The QDash record stays authoritative whether or not a message is sent.

A session lifecycle message announces that an approved session started or ended (completed,
cancelled, or expired). Its values come from QDash's records and are sent as Slack
``plain_text``, so no recorded text is read as Slack formatting or a link.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import quote

from slack_sdk import WebClient

from qdash.config import Settings, get_settings

if TYPE_CHECKING:
    from qdash.datamodel.agent_session import AgentSessionNotification
    from qdash.dbmodel.agent_session import AgentInterventionDocument, AgentSessionDocument

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


# Session lifecycle titles and colours. The colours follow the execution status palette the
# session badges use (sessionStatusBadgeClass in
# ui/src/components/features/execution/agentSessionDisplay.ts).
SESSION_EVENT_STYLES: dict[str, tuple[str, str]] = {
    "started": ("Agent session started", "#3a5ccc"),
    "completed": ("Agent session completed", "#18794e"),
    "cancelled": ("Agent session cancelled", "#6b7280"),
    "expired": ("Agent session expired", "#6b7280"),
}
MAX_FIELD_CHARS = 200


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

    @property
    def settings(self) -> Settings:
        """The settings the notifier sends with."""
        return self._settings

    def client(self) -> SlackPoster:
        """The Slack client: the test override, or the bot client with a 5 s timeout."""
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
        response = self.client().chat_postMessage(
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
        self.client().chat_postMessage(
            channel=doc.notification.channel_id,
            thread_ts=doc.notification.message_ts,
            text=f"{escape(text, quote=False)} <{url}|Open in QDash>",
            unfurl_links=False,
        )


def _plain(label: str, value: str | None) -> dict[str, Any]:
    text = _excerpt(f"{label}: {value or '-'}", MAX_FIELD_CHARS)
    return {"type": "plain_text", "text": text, "emoji": False}


def session_page_url(public_url: str, doc: AgentSessionDocument) -> str:
    """The session's policy and audit page, with the project selected."""
    return (
        f"{public_url.rstrip('/')}/agent-sessions/{quote(doc.session_id, safe='')}"
        f"?project={quote(doc.project_id, safe='')}"
    )


def session_graph_url(public_url: str, doc: AgentSessionDocument) -> str:
    """The session's graph on the Execution page, with the project selected."""
    return (
        f"{public_url.rstrip('/')}/execution/{quote(doc.chip_id, safe='')}"
        f"/sessions/{quote(doc.session_id, safe='')}?project={quote(doc.project_id, safe='')}"
    )


def post_session_event(
    notifier: AgentInterventionSlackNotifier,
    doc: AgentSessionDocument,
    notification: AgentSessionNotification,
    *,
    project_name: str,
    facts: list[tuple[str, str]],
    thread: tuple[str, str] | None = None,
) -> tuple[str, str]:
    """Post one lifecycle message and return its channel and timestamp. Raises on failure.

    An end message replies in the start message's thread, broadcast to the channel, when the
    start message was sent, so the two stay linked.
    """
    settings = notifier.settings
    event = notification.event.value
    title, color = SESSION_EVENT_STYLES.get(event, (f"Agent session {event}", "#9ca3af"))
    audit = escape(session_page_url(settings.public_url, doc), quote=False)
    graph = escape(session_graph_url(settings.public_url, doc), quote=False)
    fields = [
        _plain("Project", project_name),
        _plain("Environment", settings.env),
        _plain("Chip", doc.chip_id),
        _plain("Targets", ", ".join(doc.policy.qids)),
        _plain("Created by", doc.created_by),
        _plain("Session", doc.session_id),
        *(_plain(label, value) for label, value in facts),
    ]
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*<{audit}|{title}>*  <{graph}|Graph>",
            },
        },
        # Slack allows at most ten fields in one section.
        *(
            {"type": "section", "fields": fields[index : index + 10]}
            for index in range(0, len(fields), 10)
        ),
    ]
    kwargs: dict[str, Any] = {
        "channel": thread[0] if thread else settings.slack_agent_channel_id,
        "text": escape(f"{title}: {doc.chip_id} {', '.join(doc.policy.qids)}", quote=False),
        "attachments": [{"color": color, "blocks": blocks}],
        "unfurl_links": False,
    }
    if thread:
        kwargs |= {"thread_ts": thread[1], "reply_broadcast": True}
    response = notifier.client().chat_postMessage(**kwargs)
    return str(response["channel"]), str(response["ts"])
