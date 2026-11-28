"""The Forum thread QDash opens for each agent intervention.

When an agent asks for an expert (an intervention, from ``create_intervention`` or an
authorized ``request_human`` action), QDash opens one root thread in the project's Forum so
the question can be discussed and labelled with the team's other threads. The thread only
mirrors the request: answering, resuming, and stopping stay on the intervention page, and a
reply in the thread changes nothing.

Exactly one thread per intervention:

- The intervention record carries ``forum_thread`` from the moment it is accepted, in the
  same write that records it (or pauses the session), so a crash before the thread exists
  leaves a pending attempt. The API's sweeper retries due attempts whether or not Slack is
  configured, with a capped backoff and no limit on attempts.
- An attempt takes a lease on the record, so two API workers do not build the same thread.
  The lease claims an attempt number, and an attempt records its outcome only while that
  number is still the record's claim: an attempt whose lease expired cannot overwrite the
  outcome of a newer one.
- The thread carries the intervention id in ``agent_intervention_id``, which a unique index
  keeps to one thread. A crash after the insert, or a racing attempt whose lease expired,
  finds that thread and records it instead of inserting another.
- A recorded link is final: archiving or deleting the thread never opens a new one.

A failed attempt is recorded on the intervention and never changes the session or the
intervention's status.

The content is written by QDash for the agent, under the system ``qdash`` author, and says
so. The agent's own text is backslash-escaped so Markdown renders no links, images, HTML,
headings, or code from it. The Forum renderer still highlights ``@name`` words in the
rendered text; that is only styling, and opening the thread sends no mention notifications.
Links point only to QDash pages and to task results and executions found in the
intervention's project now. The whole body fits the Forum's content limit
(``MAX_CONTENT_CHARS``), so the thread stays editable; text that does not fit is shortened,
and the intervention page keeps the full record.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

from bunnet import SortDirection
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.api.services.agent_intervention_service import (
    DELIVERY_LEASE,
    _delivery_backoff,
    _short_error,
)
from qdash.api.services.agent_intervention_slack import REASON_LABELS
from qdash.api.services.forum_service import (
    LIVE_LABEL_FILTER,
    ForumService,
    _normalize_forum_target,
)
from qdash.common.utils.datetime import ensure_timezone, now
from qdash.datamodel.agent_session import (
    AgentForumThreadStatus,
    model_label,
)
from qdash.dbmodel.agent_session import AgentInterventionDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.forum import ForumCategoryDocument, ForumLabelDocument, ForumPostDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)

# The system author of QDash-generated Forum content; the Forum UI shows it as the bot.
AGENT_THREAD_AUTHOR = "qdash"
# Default label keys applied when the project still has a live label with that key.
AGENT_THREAD_LABELS = ("agent", "calibration", "question")
# Categories tried after the target's own category, before the first active one.
FALLBACK_CATEGORIES = ("system", "other")
MAX_TITLE_CHARS = 200
MAX_TEXT_CHARS = 2000
MAX_FIELD_CHARS = 200
MAX_ATTEMPTS_SHOWN = 10
# The Forum's limit on a post's Markdown content (ForumPostCreate and ForumPostUpdate).
MAX_CONTENT_CHARS = 8000

# Every character that can start Markdown or GFM syntax: emphasis, code, links, images,
# HTML, headings, lists, tables, entities, and autolinks (``:``, ``.``, and ``@``).
_MARKDOWN_SYNTAX = re.compile(r"([\\`*_{}\[\]()<>#+\-.!|~:@&$=])")


@dataclass(frozen=True)
class _Evidence:
    """References of an intervention that were found in its project."""

    tasks: set[str]
    # Execution id -> the chip its page lives under.
    executions: dict[str, str]
    # The latest cited task result, shown as the thread's "about" result.
    about_task_id: str | None


def _bounded(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def _inline(value: str | None, limit: int = MAX_FIELD_CHARS) -> str:
    """One line of untrusted text, escaped so Markdown renders it literally."""
    text = " ".join((value or "").split())
    return _MARKDOWN_SYNTAX.sub(r"\\\1", _bounded(text, limit)) if text else "-"


def _block(value: str | None, limit: int = MAX_TEXT_CHARS) -> str:
    """Multi-line untrusted text, escaped line by line, keeping its paragraphs."""
    lines = [" ".join(line.split()) for line in _bounded(value or "", limit).splitlines()]
    escaped = [_MARKDOWN_SYNTAX.sub(r"\\\1", line) for line in lines]
    text = "\n".join(escaped).strip()
    # Collapse runs of blank lines; keep single line breaks as hard breaks.
    paragraphs = [p.replace("\n", "  \n") for p in re.split(r"\n\s*\n", text) if p.strip()]
    return "\n\n".join(paragraphs) if paragraphs else "-"


def _fit_block(value: str, budget: int) -> str | None:
    """``_block`` of the longest prefix of *value* whose rendering fits *budget*.

    The text is cut before it is escaped, so no escape sequence or Markdown is split.
    ``None`` when not even a short prefix fits.
    """
    if len(_block(value)) <= budget:
        return _block(value)
    low, high, best = 4, min(len(value.strip()), MAX_TEXT_CHARS), None
    while low <= high:
        middle = (low + high) // 2
        rendered = _block(value, middle)
        if len(rendered) <= budget:
            best, low = rendered, middle + 1
        else:
            high = middle - 1
    return best


def _share(needs: list[int], total: int) -> list[int]:
    """Split *total* between parts fairly; a part needing less than its share frees the rest."""
    shares = [0] * len(needs)
    open_parts = [i for i, need in enumerate(needs) if need > 0]
    left = max(total, 0)
    while open_parts:
        each = left // len(open_parts)
        satisfied = [i for i in open_parts if needs[i] <= each]
        if not satisfied:
            for i in open_parts:
                shares[i] = each
            break
        for i in satisfied:
            shares[i] = needs[i]
            left -= needs[i]
        open_parts = [i for i in open_parts if i not in satisfied]
    return shares


def _path(*parts: str) -> str:
    return "/" + "/".join(quote(part, safe="") for part in parts)


def _project_query(project_id: str) -> str:
    return f"?project={quote(project_id, safe='')}"


def _iso(value: datetime | None) -> str:
    aware = ensure_timezone(value)
    return aware.isoformat(timespec="seconds") if aware is not None else "-"


class AgentInterventionForumService:
    """Open and record the Forum thread of each agent intervention."""

    def __init__(self, forum: ForumService | None = None) -> None:
        """Initialize with the Forum service whose category, label, and number rules apply."""
        self._forum = forum or ForumService()

    @staticmethod
    def _collection() -> Any:
        return AgentInterventionDocument.get_motor_collection()

    # ------------------------------------------------------------------ delivery

    def ensure_thread(self, intervention_id: str) -> None:
        """Make one attempt at a due thread, recording its outcome. Never raises."""
        try:
            self._ensure(intervention_id)
        except Exception:
            logger.exception(
                "Agent intervention %s: Forum thread bookkeeping failed", intervention_id
            )

    def _ensure(self, intervention_id: str) -> None:
        timestamp = now()
        leased = self._collection().find_one_and_update(
            {"intervention_id": intervention_id, **self._due_filter(timestamp)},
            {
                "$set": {
                    "forum_thread.status": AgentForumThreadStatus.CREATING.value,
                    "forum_thread.lease_until": timestamp + DELIVERY_LEASE,
                    "forum_thread.last_attempt_at": timestamp,
                },
                "$inc": {"forum_thread.attempts": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if leased is None:
            return
        # The claim fences this attempt's outcome: see ``_finish``.
        attempts = int(leased["forum_thread"]["attempts"])
        doc = AgentInterventionDocument.find_one({"intervention_id": intervention_id}).run()
        if doc is None or doc.forum_thread is None:
            return
        state = doc.forum_thread
        if state.post_id:
            # A crash after the link was stored but before the attempt was finished.
            self._finish(
                intervention_id,
                attempts,
                {"forum_thread.status": AgentForumThreadStatus.CREATED.value},
            )
            return
        try:
            post = self._existing_thread(doc) or self._insert_thread(doc)
        except Exception as exc:
            self._finish(
                intervention_id,
                attempts,
                {
                    "forum_thread.status": AgentForumThreadStatus.PENDING.value,
                    "forum_thread.last_error": _short_error(exc),
                    "forum_thread.next_attempt_at": now() + _delivery_backoff(attempts),
                },
            )
            logger.warning(
                "Agent intervention %s: Forum thread attempt %d failed: %s",
                intervention_id,
                attempts,
                _short_error(exc),
            )
            return
        self._finish(
            intervention_id,
            attempts,
            {
                "forum_thread.status": AgentForumThreadStatus.CREATED.value,
                "forum_thread.post_id": str(post.id),
                "forum_thread.number": post.number,
                "forum_thread.created_at": post.system_info.created_at,
                "forum_thread.last_error": "",
                "forum_thread.next_attempt_at": None,
            },
        )

    @staticmethod
    def _due_filter(timestamp: datetime) -> dict[str, Any]:
        return {
            "$or": [
                {
                    "forum_thread.status": AgentForumThreadStatus.PENDING.value,
                    "$or": [
                        {"forum_thread.next_attempt_at": None},
                        {"forum_thread.next_attempt_at": {"$lte": timestamp}},
                    ],
                },
                {
                    "forum_thread.status": AgentForumThreadStatus.CREATING.value,
                    "forum_thread.lease_until": {"$lt": timestamp},
                },
            ]
        }

    def _finish(self, intervention_id: str, attempts: int, fields: dict[str, Any]) -> None:
        """Record an attempt's outcome while its claim, attempt number *attempts*, stands.

        A newer attempt claims the record only after this attempt's lease expired; it
        increments ``attempts``, and from then on this attempt's outcome is dropped, so it
        cannot replace a newer result or release a newer lease. A thread this attempt
        inserted is not lost: the next attempt finds it by its intervention id.
        """
        result = self._collection().update_one(
            {
                "intervention_id": intervention_id,
                "forum_thread.status": AgentForumThreadStatus.CREATING.value,
                "forum_thread.attempts": attempts,
            },
            {"$set": {**fields, "forum_thread.lease_until": None}},
        )
        if result.matched_count == 0:
            logger.warning(
                "Agent intervention %s: Forum thread attempt %d lost its lease; "
                "its outcome was not recorded",
                intervention_id,
                attempts,
            )

    @staticmethod
    def _existing_thread(doc: AgentInterventionDocument) -> ForumPostDocument | None:
        """The thread an earlier attempt inserted, archived or not."""
        return ForumPostDocument.find_one(
            {"project_id": doc.project_id, "agent_intervention_id": doc.intervention_id}
        ).run()

    def _insert_thread(self, doc: AgentInterventionDocument) -> ForumPostDocument:
        chip_id, target_type, target_id = _normalize_forum_target(
            chip_id=doc.chip_id,
            target_type=self._target_type(doc.qids[0]) if len(doc.qids) == 1 else None,
            target_id=doc.qids[0] if len(doc.qids) == 1 else None,
        )
        category = self._category(doc.project_id, target_type)
        evidence = self._evidence(doc)
        post = ForumPostDocument(
            project_id=doc.project_id,
            number=self._forum._next_thread_number(doc.project_id),
            category=category,
            user_id=None,
            username=AGENT_THREAD_AUTHOR,
            title=self.title(doc),
            content=self.content(doc, evidence),
            labels=self._labels(doc.project_id),
            status="open",
            chip_id=chip_id,
            target_type=target_type,
            target_id=target_id,
            task_id=evidence.about_task_id,
            agent_intervention_id=doc.intervention_id,
            agent_session_id=doc.session_id,
        )
        try:
            post.insert()
        except DuplicateKeyError:
            # Another attempt inserted the thread first; record that one.
            existing = self._existing_thread(doc)
            if existing is None:
                raise
            return existing
        return post

    # ------------------------------------------------------------------ sweep

    def sweep(self, *, limit: int = 20) -> int:
        """Attempt every due thread; used by the API's background sweeper."""
        timestamp = now()
        docs = cast(
            "list[AgentInterventionDocument]",
            AgentInterventionDocument.find(
                self._due_filter(timestamp),
                sort=[("forum_thread.next_attempt_at", SortDirection.ASCENDING)],
                limit=limit,
            ).run(),
        )
        for doc in docs:
            self.ensure_thread(doc.intervention_id)
        return len(docs)

    # ------------------------------------------------------------------ project rules

    @staticmethod
    def _target_type(qid: str) -> str:
        # The Forum's own rule for a task result's target (ForumService.create_post).
        return "coupling" if "-" in qid else "qubit"

    def _category(self, project_id: str, target_type: str | None) -> str:
        """An active category of the project: the target's, then a fallback, then the first.

        Categories are the project's to edit, so none is created or unarchived here, except
        the defaults of a project that has no category at all, as the Forum itself does.
        """
        self._forum._ensure_default_categories(project_id)
        active: list[str] = [
            str(category.key)
            for category in ForumCategoryDocument.find(
                {"project_id": project_id, "is_archived": False}
            )
            .sort(
                [
                    ("sort_order", SortDirection.ASCENDING),
                    ("system_info.created_at", SortDirection.ASCENDING),
                ]
            )
            .to_list()
        ]
        preferred: list[str] = [target_type] if target_type else []
        for key in [*preferred, *FALLBACK_CATEGORIES]:
            if key in active:
                return key
        if not active:
            raise RuntimeError("The project has no active Forum category")
        return active[0]

    @staticmethod
    def _labels(project_id: str) -> list[str]:
        """The agent labels that are live in the project; a deleted one is left off."""
        # Insert-only, so a deleted or renamed default stays as the project left it.
        ForumService._ensure_default_labels(project_id)
        live = {
            label.key
            for label in ForumLabelDocument.find(
                {
                    "project_id": project_id,
                    "key": {"$in": list(AGENT_THREAD_LABELS)},
                    **LIVE_LABEL_FILTER,
                }
            ).to_list()
        }
        return [key for key in AGENT_THREAD_LABELS if key in live]

    # ------------------------------------------------------------------ content

    def _evidence(self, doc: AgentInterventionDocument) -> _Evidence:
        """The intervention's task results and executions that exist in its project now."""
        task_ids = [a.task_id for a in doc.attempts if a.task_id]
        execution_ids = [a.execution_id for a in doc.attempts if a.execution_id]
        tasks = (
            {
                task.task_id
                for task in TaskResultHistoryDocument.find(
                    {"project_id": doc.project_id, "task_id": {"$in": task_ids}}
                ).to_list()
            }
            if task_ids
            else set()
        )
        executions = (
            {
                execution.execution_id: execution.chip_id
                for execution in ExecutionHistoryDocument.find(
                    {"project_id": doc.project_id, "execution_id": {"$in": execution_ids}}
                ).to_list()
            }
            if execution_ids
            else {}
        )
        about = next((t for t in reversed(task_ids) if t in tasks), None)
        return _Evidence(tasks=tasks, executions=executions, about_task_id=about)

    @staticmethod
    def title(doc: AgentInterventionDocument) -> str:
        """A plain-text title naming the agent, the chip and targets, and the question."""
        targets = ", ".join(doc.qids[:4]) + (" ..." if len(doc.qids) > 4 else "")
        scope = " ".join(part for part in (doc.chip_id, targets) if part)
        question = " ".join(doc.question.split())
        return _bounded(f"Agent question ({scope}): {question}", MAX_TITLE_CHARS)

    @staticmethod
    def content(doc: AgentInterventionDocument, evidence: _Evidence) -> str:
        """The thread body as Markdown of at most ``MAX_CONTENT_CHARS``; agent text is escaped.

        The attribution, with the intervention link, and the details, with the session
        links, are always kept. When the rest does not fit, the question, the summary, and
        the evidence share the remaining room: the question and summary are shortened, and
        evidence entries are dropped whole from the end, each with a pointer to the
        intervention page.
        """
        project = _project_query(doc.project_id)
        intervention_link = (
            _path("agent-sessions", doc.session_id, "interventions", doc.intervention_id) + project
        )
        intervention_page = f"[intervention page]({intervention_link})"
        session_link = _path("agent-sessions", doc.session_id) + project
        graph_link = _path("execution", doc.chip_id, "sessions", doc.session_id) + project
        reason = REASON_LABELS.get(doc.reason.value, doc.reason.value)
        origin = (
            "a `request_human` action" if doc.action_id else "an intervention the agent recorded"
        )
        attribution = (
            f"> QDash opened this thread for a calibration agent's request for an expert "
            f"({origin}). The question and summary below are the agent's words. The "
            f"{intervention_page} shows the request's current status and is where to answer, "
            f"resume, or stop the session: replies here do not change the session."
        )
        details = [
            f"- **Reason:** {_inline(reason)}",
            f"- **Chip:** {_inline(doc.chip_id)}",
            f"- **Targets:** {_inline(', '.join(doc.qids)) if doc.qids else '-'}",
        ]
        if doc.task_name:
            details.append(f"- **Task:** {_inline(doc.task_name)}")
        if doc.node_id:
            details.append(f"- **Plan node:** {_inline(doc.node_id)}")
        details += [
            f"- **Session:** [{_inline(doc.session_id)}]({session_link}) "
            f"([graph]({graph_link})), run by {_inline(doc.created_by)}",
            f"- **Agent model:** {_inline(model_label(doc.model) or 'not reported')}",
            f"- **Recorded:** {_iso(doc.created_at)}",
        ]
        if doc.action_id:
            details.append(f"- **Action:** {_inline(doc.action_id)} (see the session audit)")

        entries = AgentInterventionForumService._evidence_entries(doc, evidence, project)
        shortened = f"(Shortened. The full text is on the {intervention_page}.)"

        def more(hidden: int) -> str:
            noun = "attempt is" if hidden == 1 else "attempts are"
            return f"{hidden} more {noun} on the {intervention_page}."

        def assemble(question: str, summary: str, evidence_lines: list[str]) -> str:
            lines = [attribution, "", "### Question", "", question, "", "### Summary", ""]
            lines += [summary, "", "### Details", "", *details, "", "### Evidence", ""]
            lines += evidence_lines
            return "\n".join(lines).strip() + "\n"

        def evidence_lines(kept: list[str]) -> list[str]:
            hidden = len(doc.attempts) - len(kept)
            return [*kept, *([""] if kept and hidden else []), *([more(hidden)] if hidden else [])]

        def evidence_within(budget: int | None) -> list[str]:
            """Whole entries, in order, while they and the "more" line fit *budget*."""
            if not doc.attempts:
                return ["The agent cited no task results or executions."]
            kept: list[str] = []
            for entry in entries:
                candidate = [*kept, entry]
                if budget is not None and len("\n".join(evidence_lines(candidate))) > budget:
                    break
                kept = candidate
            return evidence_lines(kept)

        question_full, summary_full = _block(doc.question), _block(doc.summary)
        evidence_full = evidence_within(None)
        full = assemble(question_full, summary_full, evidence_full)
        if len(full) <= MAX_CONTENT_CHARS:
            return full

        # Room left after the fixed parts, with the "shortened" notes and the "more" line
        # reserved, so every part's pointer to the intervention page always fits. Each note
        # follows its text after a blank line ("\n\n"), and so does the "more" line after
        # the kept entries. Nonempty evidence also adds one line break after the heading,
        # which ``fixed`` does not count because ``assemble`` strips the trailing blank line.
        fixed = len(assemble("", "", []))
        more_line = len(more(len(doc.attempts))) + 2
        reserve = 2 * (len(shortened) + 2) + more_line + 1
        question_share, summary_share, evidence_share = _share(
            [len(question_full), len(summary_full), len("\n".join(evidence_full))],
            MAX_CONTENT_CHARS - fixed - reserve,
        )

        def fitted(full_text: str, value: str, share: int) -> str:
            if len(full_text) <= share:
                return full_text
            prefix = _fit_block(value, share)
            return f"{prefix}\n\n{shortened}" if prefix else shortened

        content = assemble(
            fitted(question_full, doc.question, question_share),
            fitted(summary_full, doc.summary, summary_share),
            evidence_within(evidence_share + more_line),
        )
        if len(content) <= MAX_CONTENT_CHARS:
            return content
        # Only reachable with pathological identifiers in the details: keep the links.
        return (
            "\n".join(
                [
                    attribution,
                    "",
                    f"The request did not fit in a Forum post; see the {intervention_page} and "
                    f"the [session]({session_link}).",
                ]
            )
            + "\n"
        )[:MAX_CONTENT_CHARS]

    @staticmethod
    def _evidence_entries(
        doc: AgentInterventionDocument, evidence: _Evidence, project: str
    ) -> list[str]:
        """One Markdown list entry per cited attempt (up to ``MAX_ATTEMPTS_SHOWN``)."""
        entries: list[str] = []
        for index, attempt in enumerate(doc.attempts[:MAX_ATTEMPTS_SHOWN], start=1):
            what = " on ".join(part for part in (attempt.task_name, attempt.qid) if part)
            reported = ", ".join(
                f"{label} {_inline(value, 64)}"
                for label, value in (
                    ("transition", attempt.transition),
                    ("status", attempt.status),
                )
                if value
            )
            entry = f"{index}. {_inline(what) if what else 'Attempt'}"
            if reported:
                entry += f" (reported {reported})"
            links: list[str] = []
            if attempt.task_id:
                links.append(
                    f"[task result]({_path('task-results', attempt.task_id)}{project})"
                    if attempt.task_id in evidence.tasks
                    else f"task result {_inline(attempt.task_id)} (not found)"
                )
            if attempt.execution_id:
                chip = evidence.executions.get(attempt.execution_id)
                links.append(
                    f"[execution]({_path('execution', chip, attempt.execution_id)}{project})"
                    if chip
                    else f"execution {_inline(attempt.execution_id)} (not found)"
                )
            if attempt.evaluation_id:
                links.append(f"evaluation {_inline(attempt.evaluation_id)}")
            if links:
                entry += ": " + ", ".join(links)
            if attempt.reason:
                entry += f"\n   - Agent's note: {_inline(attempt.reason, 500)}"
            entries.append(entry)
        return entries
