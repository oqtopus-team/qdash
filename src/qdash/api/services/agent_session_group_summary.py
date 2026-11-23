"""One agent session's group header, shared by the grouped Execution list and the session graph.

Both views count a session's measurements the same way: an authorized ``run_task`` action that
was dispatched, numbered in dispatch order with a per-target attempt. An action whose execution
is in a link conflict (``agent_execution_links``) is never counted as a measurement and is named
in ``missing`` instead. Records the session counted but has not written yet are read from its
pending payload in memory only; nothing here writes.
"""

from __future__ import annotations

from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from qdash.api.schemas.execution_group import AgentSessionGroupCounts, AgentSessionGroupSummary
from qdash.api.services.agent_execution_links import (
    DISPATCH_IN_PROGRESS,
    OPEN_EXECUTION_STATUSES,
    ExecutionLink,
    UnlinkedAction,
    effective_session_status,
    utc,
)
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentInterventionStatus,
    model_label,
)
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.api.schemas.execution import CalibrationSessionRef

MAX_MISSING = 10
UNANSWERED_INTERVENTION_STATUSES = frozenset(
    {AgentInterventionStatus.OPEN.value, AgentInterventionStatus.RESPONDING.value}
)
EPOCH = datetime.min.replace(tzinfo=UTC)


def action_key(action: AgentActionDocument) -> tuple[int, datetime, str]:
    # State versions are strictly increasing within a session, so they order its actions.
    return (action.state_version_before, utc(action.created_at) or EPOCH, action.action_id)


def is_measurement(action: AgentActionDocument) -> bool:
    return (
        action.action_type == AgentActionType.RUN_TASK
        and action.decision == AgentActionDecision.AUTHORIZED
    )


def is_dispatched(action: AgentActionDocument) -> bool:
    return bool(action.operation_id or action.execution_id)


def measurement_numbers(
    actions: list[AgentActionDocument], unlinked: Mapping[str, UnlinkedAction]
) -> dict[str, tuple[int, int]]:
    """Dispatch order and per-target attempt of every dispatched measurement.

    An action in a link conflict gets no number: no execution can be attributed to it, so it
    is not counted as a measurement in either the list or the graph.
    """
    numbers: dict[str, tuple[int, int]] = {}
    attempts: Counter[tuple[str | None, tuple[str, ...]]] = Counter()
    for action in sorted(actions, key=action_key):
        if not is_measurement(action) or not is_dispatched(action):
            continue
        if action.action_id in unlinked:
            continue
        target = (action.task_name, tuple(action.qids))
        attempts[target] += 1
        numbers[action.action_id] = (len(numbers) + 1, attempts[target])
    return numbers


def _conflict_text(item: UnlinkedAction) -> str:
    if item.reason == "ambiguous":
        return (
            f"execution of action {item.action_id}: its ids name different executions "
            f"({', '.join(item.execution_ids)})"
        )
    holder = item.holder
    held_by = f"action {holder.action_id}" if holder else "another action"
    if holder is not None and holder.session_id != item.session_id:
        held_by += f" of session {holder.session_id}"
    return f"execution of action {item.action_id}: {item.execution_ids[0]} is held by {held_by}"


def _pending_records(session: AgentSessionDocument) -> list[str]:
    """Records the session counted but has not written to their collections yet."""
    pending: list[str] = []
    if session.pending_action and session.pending_action.get("action_id"):
        pending.append(f"action record {session.pending_action['action_id']} (pending write)")
    intervention = (session.pending_intervention or {}).get("intervention") or {}
    if intervention.get("intervention_id"):
        pending.append(f"intervention record {intervention['intervention_id']} (pending write)")
    return pending


def with_pending(
    session: AgentSessionDocument, actions: list[AgentActionDocument]
) -> list[AgentActionDocument]:
    """The action records plus, in memory only, the ones the session has yet to write."""
    listed = {a.action_id for a in actions}
    extra: list[dict[str, Any]] = []
    if session.pending_action:
        extra.append(session.pending_action)
    pending_pause_action = (session.pending_intervention or {}).get("action")
    if pending_pause_action:
        extra.append(pending_pause_action)
    merged = list(actions)
    for payload in extra:
        if payload.get("action_id") in listed:
            continue
        with suppress(ValueError):
            merged.append(AgentActionDocument.model_validate(payload))
            listed.add(str(payload.get("action_id")))
    return merged


def session_summary(
    session: AgentSessionDocument,
    *,
    actions: list[AgentActionDocument],
    links: list[ExecutionLink],
    unlinked: Mapping[str, UnlinkedAction],
    open_interventions: int,
    decisions: int,
    calibration_session: CalibrationSessionRef | None = None,
) -> AgentSessionGroupSummary:
    """The group header of one session, from its records only."""
    linked_actions = {link.action_id for link in links}
    measurements = [a for a in actions if is_measurement(a)]
    pending = 0
    failed_dispatch = 0
    in_flight = sum(1 for link in links if link.status in OPEN_EXECUTION_STATUSES)
    missing: list[str] = _pending_records(session)
    for action in measurements:
        if action.action_id in linked_actions:
            continue
        conflict = unlinked.get(action.action_id)
        if conflict is not None:
            # Dispatched, but its execution cannot be attributed to it: neither pending nor
            # failed, and never counted as a measurement.
            missing.append(_conflict_text(conflict))
        elif action.execution_status in DISPATCH_IN_PROGRESS:
            pending += 1
            in_flight += 1
        elif action.operation_id or action.execution_id:
            # Dispatched, but no execution on the session's chip names it (yet).
            pending += 1
            missing.append(f"execution of action {action.action_id}")
        elif action.execution_status == "not_started":
            pending += 1
        else:
            failed_dispatch += 1
    starts = [link.start_at for link in links if link.start_at is not None]
    created = cast("datetime", utc(session.created_at))
    return AgentSessionGroupSummary(
        session_id=session.session_id,
        project_id=session.project_id,
        chip_id=session.chip_id,
        created_by=session.created_by,
        created_at=created,
        updated_at=cast("datetime", utc(session.updated_at)),
        expires_at=cast("datetime", utc(session.expires_at)),
        status=effective_session_status(session.status, session.expires_at),
        stored_status=session.status,
        active_intervention_id=session.active_intervention_id,
        qids=list(session.policy.qids),
        allowed_tasks=list(session.policy.allowed_tasks),
        autonomy=session.policy.autonomy.value,
        skill_name=session.skill_name,
        model=session.model,
        model_name=model_label(session.model),
        calibration_session=calibration_session,
        counts=AgentSessionGroupCounts(
            actions=session.action_count,
            max_actions=session.policy.max_actions,
            measurements=len(links),
            pending_dispatch=pending,
            dispatch_failed=failed_dispatch,
            in_flight=in_flight,
            rejected_proposals=sum(
                1 for a in actions if a.decision == AgentActionDecision.REJECTED
            ),
            open_interventions=open_interventions,
            decisions=decisions,
        ),
        latest_activity_at=max([created, *starts]),
        missing=missing[:MAX_MISSING],
    )
