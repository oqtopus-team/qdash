"""Which real executions an agent session dispatched, from the session's action records.

An agent session never owns an execution the way a pipeline flow run does: each authorized
``run_task`` action dispatches one ordinary execution and records its Prefect flow run id
(``operation_id``) and, once resolved, its QDash ``execution_id``. Those action fields are the
only authority this module uses. The ``agent-session:<id>`` tag the dispatch adds to an
execution is a hint for people, not a link: an execution that carries the tag without an action
naming it stays an ordinary execution.

An execution belongs to at most one session. The link must also stay inside one project and
one chip: the execution is looked up in the session's project and on the session's chip, so an
action whose operation resolves elsewhere links nothing.

The resolution is deterministic and shared by the grouped list, the execution detail, and the
session graph and audit measurement attribution:

- An action resolves through its ``operation_id`` first, then its ``execution_id``. A flow run
  id that several executions carry resolves to the earliest of them by ``start_at``, then by
  ``execution_id``; a key that is some execution's own ``execution_id`` resolves to that one.
- An action whose ``operation_id`` and ``execution_id`` resolve to two different executions on
  the chip is ambiguous: it links neither, and is reported as ``ambiguous``.
- Actions are taken in order of ``created_at``, then ``state_version_before``, then
  ``action_id``. Each execution goes to the first action that resolves to it, in this or any
  other session of the chip; a later action that resolves to it is reported as ``claimed``,
  with the action that holds it.

An unlinked action is never reported as not dispatched: its own dispatch fields still say it
was, and the readers show it as a link conflict, without an execution or a task result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from qdash.api.schemas.execution_group import ExecutionAgentSessionLink
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentSessionStatus,
    model_label,
)
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument

if TYPE_CHECKING:
    from collections.abc import Iterable

AGENT_SESSION_TAG_PREFIX = "agent-session:"
OPEN_EXECUTION_STATUSES = frozenset({"running", "scheduled", "cancelling"})
# Dispatch states of an action whose measurement has not produced an execution record yet.
DISPATCH_IN_PROGRESS = frozenset({"dispatching", "queued"})
ENDED_SESSION_STATUSES = frozenset(
    {AgentSessionStatus.COMPLETED, AgentSessionStatus.CANCELLED, AgentSessionStatus.EXPIRED}
)


def utc(value: datetime | None) -> datetime | None:
    """An aware UTC datetime; stored datetimes are read back naive."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def effective_session_status(
    status: AgentSessionStatus, expires_at: datetime | None, *, at: datetime | None = None
) -> AgentSessionStatus:
    """The session's state as a read sees it, without writing anything.

    An active or paused session past its expiry is expired, as ``load_agent_session`` would
    record on its next load.
    """
    expiry = utc(expires_at)
    if (
        status in {AgentSessionStatus.ACTIVE, AgentSessionStatus.WAITING_FOR_HUMAN}
        and expiry is not None
        and expiry <= (at or now())
    ):
        return AgentSessionStatus.EXPIRED
    return status


@dataclass(frozen=True)
class ExecutionLink:
    """One real execution an action of a session dispatched."""

    session_id: str
    action_id: str
    execution_id: str
    status: str
    start_at: datetime | None


@dataclass(frozen=True)
class UnlinkedAction:
    """A dispatched action that names an execution on the chip but holds none.

    ``claimed``: the execution it resolves to is held by an earlier action, ``holder``.
    ``ambiguous``: its operation and execution ids resolve to different executions.
    """

    session_id: str
    action_id: str
    reason: Literal["claimed", "ambiguous"]
    execution_ids: tuple[str, ...]
    holder: ExecutionLink | None = None


@dataclass
class ChipLinks:
    """Every agent session of one chip and the executions their actions dispatched."""

    session_created: dict[str, datetime] = field(default_factory=dict)
    # Status, expiry, creator, and model of each session, from the same session read.
    session_info: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_execution: dict[str, ExecutionLink] = field(default_factory=dict)
    by_session: dict[str, list[ExecutionLink]] = field(default_factory=dict)
    by_action: dict[str, ExecutionLink] = field(default_factory=dict)
    unlinked: dict[str, UnlinkedAction] = field(default_factory=dict)


def _measurement_query(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "action_type": AgentActionType.RUN_TASK.value,
        "decision": AgentActionDecision.AUTHORIZED.value,
    }


def _execution_keys(actions: Iterable[dict[str, Any]]) -> tuple[list[str], list[str]]:
    operation_ids = sorted({a["operation_id"] for a in actions if a.get("operation_id")})
    execution_ids = sorted({a["execution_id"] for a in actions if a.get("execution_id")})
    return operation_ids, execution_ids


def _find_executions(
    project_id: str, chip_id: str, operation_ids: list[str], execution_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Executions on the chip an operation or execution id names, keyed by both ids.

    ``operation_id`` is the Prefect flow run id; actions dispatched before that was fixed stored
    the QDash execution id there, so both are matched, as the session audit matches them.
    """
    if not operation_ids and not execution_ids:
        return {}
    found = list(
        ExecutionHistoryDocument.get_motor_collection().find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "$or": [
                    {"note.flow_run_id": {"$in": operation_ids}},
                    {"execution_id": {"$in": operation_ids + execution_ids}},
                ],
            },
            {"_id": 0, "execution_id": 1, "note.flow_run_id": 1, "status": 1, "start_at": 1},
        )
    )
    # A stable order, so a flow run id shared by two records always resolves to the same one.
    found.sort(
        key=lambda doc: (
            utc(doc.get("start_at")) or datetime.min.replace(tzinfo=UTC),
            str(doc.get("execution_id")),
        )
    )
    by_key: dict[str, dict[str, Any]] = {}
    for doc in found:
        by_key.setdefault(str(doc["execution_id"]), doc)
    for doc in found:
        flow_run_id = (doc.get("note") or {}).get("flow_run_id")
        if isinstance(flow_run_id, str) and flow_run_id:
            by_key.setdefault(flow_run_id, doc)
    return by_key


def _resolve(action: dict[str, Any], executions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The executions an action's ids resolve to: none, one, or two that disagree."""
    found: list[dict[str, Any]] = []
    for key in (action.get("operation_id"), action.get("execution_id")):
        doc = executions.get(key) if key else None
        if doc is not None and all(doc["execution_id"] != other["execution_id"] for other in found):
            found.append(doc)
    return found


def _assign(
    actions: list[dict[str, Any]], executions: dict[str, dict[str, Any]], links: ChipLinks
) -> None:
    """Link each execution to the earliest action that resolves to it, and only to it."""
    for action in actions:
        resolved = _resolve(action, executions)
        if not resolved:
            continue
        session_id = str(action["session_id"])
        action_id = str(action["action_id"])
        if len(resolved) > 1:
            links.unlinked[action_id] = UnlinkedAction(
                session_id=session_id,
                action_id=action_id,
                reason="ambiguous",
                execution_ids=tuple(str(doc["execution_id"]) for doc in resolved),
            )
            continue
        doc = resolved[0]
        execution_id = str(doc["execution_id"])
        if execution_id in links.by_execution:
            links.unlinked[action_id] = UnlinkedAction(
                session_id=session_id,
                action_id=action_id,
                reason="claimed",
                execution_ids=(execution_id,),
                holder=links.by_execution[execution_id],
            )
            continue
        link = ExecutionLink(
            session_id=session_id,
            action_id=action_id,
            execution_id=execution_id,
            status=str(doc.get("status") or ""),
            start_at=utc(doc.get("start_at")),
        )
        links.by_execution[execution_id] = link
        links.by_action[action_id] = link
        links.by_session.setdefault(link.session_id, []).append(link)


_ACTION_FIELDS = {
    "_id": 0,
    "action_id": 1,
    "session_id": 1,
    "operation_id": 1,
    "execution_id": 1,
    "created_at": 1,
    "state_version_before": 1,
}


_SESSION_FIELDS = {
    "session_id": 1,
    "created_at": 1,
    "status": 1,
    "expires_at": 1,
    "created_by": 1,
    "model": 1,
    # The calibration session an admitted session belongs to, for the grouped list.
    "calibration_session_id": 1,
    "calibration_admission": 1,
}


def _linked(link: ExecutionLink, session: dict[str, Any]) -> ExecutionAgentSessionLink:
    """The verified link of an execution an action of ``session`` dispatched."""
    return ExecutionAgentSessionLink(
        session_id=link.session_id,
        linked=True,
        action_id=link.action_id,
        status=effective_session_status(
            AgentSessionStatus(session["status"]), session.get("expires_at")
        ),
        created_by=session.get("created_by") or None,
        model_name=model_label(session.get("model")),
    )


def summary_link(links: ChipLinks, execution_id: str) -> ExecutionAgentSessionLink | None:
    """The verified link of one listed execution, from links already resolved for its chip.

    Only an action link counts; an ``agent-session:`` tag without one returns None, so a list
    row never shows a tagged execution as dispatched by an agent.
    """
    link = links.by_execution.get(execution_id)
    session = links.session_info.get(link.session_id) if link is not None else None
    if link is None or session is None:
        return None
    return _linked(link, session)


def _action_order(action: dict[str, Any]) -> tuple[datetime, int, str]:
    return (
        utc(action.get("created_at")) or datetime.min.replace(tzinfo=UTC),
        int(action.get("state_version_before") or 0),
        str(action.get("action_id")),
    )


def resolve_chip_links(project_id: str, chip_id: str) -> ChipLinks:
    """The chip's agent sessions and their dispatched executions, in three bounded queries.

    Only identifiers, times, and statuses are read. The cost grows with the chip's agent
    sessions and their measurements, not with its other executions.
    """
    links = ChipLinks()
    sessions = AgentSessionDocument.get_motor_collection().find(
        {"project_id": project_id, "chip_id": chip_id}, {"_id": 0, **_SESSION_FIELDS}
    )
    for doc in sessions:
        created = utc(doc.get("created_at"))
        if created is not None:
            links.session_created[str(doc["session_id"])] = created
            links.session_info[str(doc["session_id"])] = doc
    if not links.session_created:
        return links
    actions = list(
        AgentActionDocument.get_motor_collection().find(
            {
                **_measurement_query(project_id),
                "session_id": {"$in": sorted(links.session_created)},
                "$or": [{"operation_id": {"$ne": None}}, {"execution_id": {"$ne": None}}],
            },
            _ACTION_FIELDS,
        )
    )
    actions.sort(key=_action_order)
    operation_ids, execution_ids = _execution_keys(actions)
    _assign(actions, _find_executions(project_id, chip_id, operation_ids, execution_ids), links)
    return links


def keys_on_other_chips(project_id: str, chip_id: str, keys: Iterable[str]) -> set[str]:
    """Which of these operation or execution ids name an execution of the project elsewhere."""
    wanted = sorted({key for key in keys if key})
    if not wanted:
        return set()
    found: set[str] = set()
    for doc in ExecutionHistoryDocument.get_motor_collection().find(
        {
            "project_id": project_id,
            "chip_id": {"$ne": chip_id},
            "$or": [{"note.flow_run_id": {"$in": wanted}}, {"execution_id": {"$in": wanted}}],
        },
        {"_id": 0, "execution_id": 1, "note.flow_run_id": 1},
    ):
        found.add(str(doc["execution_id"]))
        flow_run_id = (doc.get("note") or {}).get("flow_run_id")
        if isinstance(flow_run_id, str):
            found.add(flow_run_id)
    return found & set(wanted)


def link_for_execution(
    project_id: str, execution: ExecutionHistoryDocument
) -> ExecutionAgentSessionLink | None:
    """The agent session an execution belongs to, or the session its tag names, or None.

    The link is resolved the way ``resolve_chip_links`` resolves it, so the execution page and
    the grouped list agree on which session, if any, holds an execution.
    """
    flow_run_id = (execution.note or {}).get("flow_run_id")
    keys = [execution.execution_id] + ([flow_run_id] if isinstance(flow_run_id, str) else [])
    candidates = list(
        AgentActionDocument.get_motor_collection().find(
            {
                **_measurement_query(project_id),
                "$or": [{"operation_id": {"$in": keys}}, {"execution_id": execution.execution_id}],
            },
            _ACTION_FIELDS,
        )
    )
    if candidates:
        session_ids = sorted({str(a["session_id"]) for a in candidates})
        sessions = {
            str(doc["session_id"]): doc
            for doc in AgentSessionDocument.get_motor_collection().find(
                {
                    "project_id": project_id,
                    "chip_id": execution.chip_id,
                    "session_id": {"$in": session_ids},
                },
                {"_id": 0, **_SESSION_FIELDS},
            )
        }
        same_chip = sorted(
            (a for a in candidates if str(a["session_id"]) in sessions), key=_action_order
        )
        if same_chip:
            # Several actions may name this execution's flow run; the earliest that resolves to
            # this very execution holds it, as in the grouped list.
            operation_ids, execution_ids = _execution_keys(same_chip)
            executions = _find_executions(
                project_id, execution.chip_id, operation_ids, execution_ids
            )
            links = ChipLinks()
            _assign(same_chip, executions, links)
            link = links.by_execution.get(execution.execution_id)
            if link is not None:
                return _linked(link, sessions[link.session_id])
    tagged = next((tag for tag in execution.tags if tag.startswith(AGENT_SESSION_TAG_PREFIX)), None)
    if tagged is None:
        return None
    session_id = tagged[len(AGENT_SESSION_TAG_PREFIX) :]
    if not session_id:
        return None
    session = AgentSessionDocument.get_motor_collection().find_one(
        {"project_id": project_id, "session_id": session_id},
        {"_id": 0, "status": 1, "expires_at": 1},
    )
    return ExecutionAgentSessionLink(
        session_id=session_id,
        linked=False,
        status=(
            effective_session_status(
                AgentSessionStatus(cast("str", session["status"])), session.get("expires_at")
            )
            if session is not None
            else None
        ),
    )
