"""The Execution list grouped by agent session, and one session's graph over its executions.

Both are read-only projections of records that already exist. Nothing here creates, schedules,
locks, or cancels an execution, and no record is changed to make a group: a session row is the
session record plus the real executions its actions dispatched (see ``agent_execution_links``),
and the graph adds the session's decisions and interventions as typed nodes and edges.

Statuses keep their owners. A group's status is the session's (``active``, ``waiting_for_human``,
``completed``, ``cancelled``, ``expired``); each child is its own execution's. A session holds no
hardware lock between measurements or while it waits for a person, and is not failed for it.
"""

from __future__ import annotations

from collections import Counter
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Any, cast

from bunnet import SortDirection
from fastapi import HTTPException

from qdash.api.schemas.execution_group import (
    AgentSessionChildExecution,
    AgentSessionGraphDecision,
    AgentSessionGraphEdge,
    AgentSessionGraphEdgeKind,
    AgentSessionGraphIntervention,
    AgentSessionGraphMeasurement,
    AgentSessionGraphNode,
    AgentSessionGraphProposal,
    AgentSessionGraphResponse,
    AgentSessionGraphSessionAction,
    AgentSessionGroupCounts,
    AgentSessionGroupSummary,
    CalibrationGroupAgentSession,
    CalibrationGroupCounts,
    CalibrationGroupPipelineRun,
    CalibrationRecommendationRef,
    CalibrationSessionGroupSummary,
    ExecutionGroupItem,
    ListExecutionGroupsResponse,
)
from qdash.api.services.agent_execution_links import (
    DISPATCH_IN_PROGRESS,
    OPEN_EXECUTION_STATUSES,
    ChipLinks,
    ExecutionLink,
    UnlinkedAction,
    effective_session_status,
    keys_on_other_chips,
    resolve_chip_links,
    summary_link,
    utc,
)
from qdash.api.services.calibration_session_groups import (
    ChipCalibrationGroups,
    RunExecution,
    resolve_chip_calibration_groups,
)
from qdash.api.services.calibration_session_links import (
    NO_RELATIONS,
    agent_session_parents,
    resolve_execution_relations,
)
from qdash.api.services.execution_service import day_window, execution_summary
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentInterventionStatus,
    model_label,
)
from qdash.datamodel.calibration_session import CalibrationSessionStatus
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentDecisionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.calibration_session import CalibrationDecisionDocument
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qdash.api.schemas.execution import CalibrationSessionRef, ExecutionResponseSummary
    from qdash.repository.execution_history import MongoExecutionHistoryRepository

# Executions one session row of the list carries; the graph lists every one.
MAX_LIST_CHILDREN = 20
# Pipeline runs and nested agent sessions one calibration session row carries.
MAX_LIST_RUNS = 20
MAX_LIST_AGENT_SESSIONS = 20
# Nodes one graph response carries; the latest are kept and the audit holds the rest.
MAX_SESSION_GRAPH_NODES = 1000
MAX_TEXT = 500
MAX_MISSING = 10
UNANSWERED_INTERVENTION_STATUSES = frozenset(
    {AgentInterventionStatus.OPEN.value, AgentInterventionStatus.RESPONDING.value}
)
_EPOCH = datetime.min.replace(tzinfo=UTC)

SESSION_GRAPH_NOTES = [
    "A live read of the session's records, collected one after another. It is not a "
    "snapshot: a status can change while it is read. The session audit offers a "
    "consistency-checked read and an export.",
    "The session's status is its own; each measurement's status is its real execution's. "
    "A session between measurements or waiting for an expert holds no hardware.",
    "Sequence edges are temporal: the next measurement dispatched. Evidence, next-action, "
    "retry, escalation, and follow-up edges come from references in the records; no "
    "scientific dependency is inferred from time.",
    "Decision text and intervention summaries are agent statements; guidance is an expert "
    "statement. Neither grants scope beyond the session policy.",
]


def run_target_qids(run: dict[str, Any]) -> list[str]:
    """The qubits QDash resolved for a dispatched run, from its stored dispatch response."""
    targets = (run.get("response") or {}).get("targets") or {}
    qids = targets.get("qids") if isinstance(targets, dict) else None
    return [str(qid) for qid in qids] if isinstance(qids, list) else []


def _run_dispatch(run: dict[str, Any]) -> str:
    """A run projection's dispatch status, stale dispatching read as unknown everywhere."""
    from qdash.api.services.calibration_session_service import DISPATCH_STALE_AFTER

    value = str(run.get("status") or "")
    updated = utc(run.get("updated_at"))
    if value == "dispatching" and updated is not None and now() - updated > DISPATCH_STALE_AFTER:
        return "unknown"
    return value


def _target_key(target: str) -> tuple[tuple[int, int | str], ...]:
    """Qubit 2 before 10, and a coupling after its control qubit."""
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in target.split("-"))


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _action_key(action: AgentActionDocument) -> tuple[int, datetime, str]:
    # State versions are strictly increasing within a session, so they order its actions.
    return (action.state_version_before, utc(action.created_at) or _EPOCH, action.action_id)


def _is_measurement(action: AgentActionDocument) -> bool:
    return (
        action.action_type == AgentActionType.RUN_TASK
        and action.decision == AgentActionDecision.AUTHORIZED
    )


def _dispatched(action: AgentActionDocument) -> bool:
    return bool(action.operation_id or action.execution_id)


def _measurement_numbers(
    actions: list[AgentActionDocument], unlinked: Mapping[str, UnlinkedAction]
) -> dict[str, tuple[int, int]]:
    """Dispatch order and per-target attempt of every dispatched measurement.

    An action in a link conflict gets no number: no execution can be attributed to it, so it
    is not counted as a measurement in either the list or the graph.
    """
    numbers: dict[str, tuple[int, int]] = {}
    attempts: Counter[tuple[str | None, tuple[str, ...]]] = Counter()
    for action in sorted(actions, key=_action_key):
        if not _is_measurement(action) or not _dispatched(action):
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


def _with_pending(
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


def _session_summary(
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
    measurements = [a for a in actions if _is_measurement(a)]
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


@dataclass
class _SessionGraphRecords:
    """One session's records for its graph, read without writing anything.

    Executions come from the chip-wide resolution the grouped list uses, so an execution is
    held by the same action in both. Task results and evaluations are read only for the
    executions an action holds: a result is never attributed through an unresolved, claimed,
    or ambiguous reference.
    """

    session: AgentSessionDocument
    actions: list[AgentActionDocument]
    decisions: list[AgentDecisionDocument]
    interventions: list[AgentInterventionDocument]
    links: list[ExecutionLink]
    unlinked: dict[str, UnlinkedAction]
    executions: dict[str, ExecutionHistoryDocument] = field(default_factory=dict)
    task_results: dict[str, TaskResultHistoryDocument] = field(default_factory=dict)
    evaluations: list[EvaluationDocument] = field(default_factory=list)
    wrong_chip: set[str] = field(default_factory=set)
    pending_action_ids: set[str] = field(default_factory=set)

    @classmethod
    def read(cls, project_id: str, session_id: str) -> _SessionGraphRecords:
        session = AgentSessionDocument.find_one(
            {"project_id": project_id, "session_id": session_id}
        ).run()
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=f"Agent session '{session_id}' not found",
            )
        scope = {"project_id": project_id, "session_id": session_id}
        stored = cast("list[AgentActionDocument]", AgentActionDocument.find(scope).run())
        actions = sorted(_with_pending(session, stored), key=_action_key)
        stored_ids = {a.action_id for a in stored}
        interventions = cast(
            "list[AgentInterventionDocument]", AgentInterventionDocument.find(scope).run()
        )
        pending_intervention = (session.pending_intervention or {}).get("intervention")
        if pending_intervention and pending_intervention.get("intervention_id") not in {
            i.intervention_id for i in interventions
        }:
            with suppress(ValueError):
                interventions.append(AgentInterventionDocument.model_validate(pending_intervention))
        decisions = cast(
            "list[AgentDecisionDocument]",
            AgentDecisionDocument.find(
                scope, sort=[("recorded_at", SortDirection.ASCENDING)]
            ).run(),
        )

        chip_links = resolve_chip_links(project_id, session.chip_id)
        own = {a.action_id for a in actions}
        records = cls(
            session=session,
            actions=actions,
            decisions=decisions,
            interventions=interventions,
            links=list(chip_links.by_session.get(session_id, [])),
            unlinked={k: v for k, v in chip_links.unlinked.items() if k in own},
            pending_action_ids=own - stored_ids,
        )

        held = {link.action_id: link.execution_id for link in records.links}
        if held:
            docs = cast(
                "list[ExecutionHistoryDocument]",
                ExecutionHistoryDocument.find(
                    {
                        "project_id": project_id,
                        "chip_id": session.chip_id,
                        "execution_id": {"$in": sorted(set(held.values()))},
                    }
                ).run(),
            )
            by_id = {doc.execution_id: doc for doc in docs}
            records.executions = {
                action_id: by_id[execution_id]
                for action_id, execution_id in held.items()
                if execution_id in by_id
            }

        # Dispatched measurements that hold nothing and are not in a conflict on the chip:
        # say so when their ids name an execution on another chip.
        unresolved = [
            a
            for a in actions
            if _is_measurement(a)
            and _dispatched(a)
            and a.action_id not in held
            and a.action_id not in records.unlinked
        ]
        elsewhere = keys_on_other_chips(
            project_id,
            session.chip_id,
            [key for a in unresolved for key in (a.operation_id, a.execution_id) if key],
        )
        records.wrong_chip = {
            a.action_id
            for a in unresolved
            if (a.operation_id in elsewhere) or (a.execution_id in elsewhere)
        }

        by_action = {a.action_id: a for a in actions}
        if records.executions:
            results = cast(
                "list[TaskResultHistoryDocument]",
                TaskResultHistoryDocument.find(
                    {
                        "project_id": project_id,
                        "chip_id": session.chip_id,
                        "execution_id": {
                            "$in": sorted({e.execution_id for e in records.executions.values()})
                        },
                    },
                    sort=[
                        ("end_at", SortDirection.ASCENDING),
                        ("task_id", SortDirection.ASCENDING),
                    ],
                ).run(),
            )
            by_key: dict[tuple[str, str, str], TaskResultHistoryDocument] = {}
            for result in results:
                # Ascending end_at, so the latest result of a task on a qubit wins, as the
                # session audit picks it.
                by_key[(result.execution_id, result.name, result.qid)] = result
            for action_id, execution in records.executions.items():
                action = by_action[action_id]
                if not action.task_name or len(action.qids) != 1:
                    continue
                matched = by_key.get((execution.execution_id, action.task_name, action.qids[0]))
                if matched is not None:
                    records.task_results[action_id] = matched

        task_ids = sorted({result.task_id for result in records.task_results.values()})
        if task_ids:
            records.evaluations = cast(
                "list[EvaluationDocument]",
                EvaluationDocument.find(
                    {"project_id": project_id, "task_id": {"$in": task_ids}},
                    sort=[("requested_at", SortDirection.ASCENDING)],
                ).run(),
            )
        return records


class ExecutionGroupService:
    """Read the Execution list grouped by agent session, and one session's graph."""

    def __init__(self, execution_history_repository: MongoExecutionHistoryRepository) -> None:
        self._history_repo = execution_history_repository

    # ------------------------------------------------------------------ list

    def list_groups(
        self,
        *,
        project_id: str,
        chip_id: str,
        skip: int = 0,
        limit: int = 20,
        date: str | None = None,
        timezone: str = "UTC",
    ) -> ListExecutionGroupsResponse:
        """A page of rows, newest first: calibration sessions, agent sessions, and executions.

        Rows are grouped before the page is cut, so a session is one row with all of its
        executions. A calibration session row holds the step executions of its pipeline runs
        and its admitted agent sessions (each nested with its own executions); an agent session
        outside one is its own row; every other execution is its own row, ordered by its start
        as in the ungrouped list. A session row is ordered by its latest activity: its latest
        execution start, or its creation before the first. With ``date``, an execution row
        needs its start on that day and a session row its creation or an execution start on
        it; the row is then ordered by its latest activity of that day and still lists every
        execution.
        """
        window = day_window(date, timezone) if date else None
        links = resolve_chip_links(project_id, chip_id)
        calib = resolve_chip_calibration_groups(project_id, chip_id, links)

        def in_window(moment: datetime | None) -> bool:
            if window is None:
                return True
            return moment is not None and window[0] <= moment < window[1]

        def agent_moments(session_id: str) -> list[datetime]:
            return [links.session_created[session_id]] + [
                link.start_at
                for link in links.by_session.get(session_id, [])
                if link.start_at is not None
            ]

        rows: list[tuple[datetime, str, str]] = []
        for session_id in links.session_created:
            if session_id in calib.agent_parent:
                continue
            moments = [m for m in agent_moments(session_id) if in_window(m)]
            if moments:
                rows.append((max(moments), "agent_session", session_id))
        for cs_id, doc in calib.sessions.items():
            moments = [utc(doc.get("created_at")) or _EPOCH]
            for run in calib.runs.get(cs_id, []):
                moments += [
                    e.start_at
                    for e in calib.run_executions.get(str(run["run_id"]), [])
                    if e.start_at is not None
                ]
            for agent_id in calib.agents.get(cs_id, []):
                moments += agent_moments(agent_id)
            moments = [m for m in moments if in_window(m)]
            if moments:
                rows.append((max(moments), "calibration_session", cs_id))
        rows.sort(key=lambda row: (row[0], row[2]), reverse=True)

        grouped_ids = sorted(set(links.by_execution) | set(calib.execution_session))
        base = self._chip_query(project_id, chip_id, window)
        collection = ExecutionHistoryDocument.get_motor_collection()
        total_executions = collection.count_documents(base)
        ungrouped = {**base, "execution_id": {"$nin": grouped_ids}}
        ungrouped_total = collection.count_documents(ungrouped)
        # The merged order needs at most skip + limit rows of each kind.
        heads = list(
            collection.find(ungrouped, {"_id": 0, "execution_id": 1, "start_at": 1})
            .sort(
                [("start_at", SortDirection.DESCENDING), ("execution_id", SortDirection.DESCENDING)]
            )
            .limit(skip + limit)
        )

        merged: list[tuple[str, str, datetime | None]] = []
        i = j = 0
        while len(merged) < skip + limit and (i < len(rows) or j < len(heads)):
            row_at = rows[i][0] if i < len(rows) else None
            head_at = utc(heads[j].get("start_at")) if j < len(heads) else None
            take_row = i < len(rows) and (
                j >= len(heads) or head_at is None or (row_at or _EPOCH) >= head_at
            )
            if take_row:
                merged.append((rows[i][1], rows[i][2], row_at))
                i += 1
            else:
                merged.append(("execution", str(heads[j]["execution_id"]), head_at))
                j += 1
        page = merged[skip : skip + limit]

        items = self._page_items(project_id, page, links, calib, in_window)
        agent_rows = sum(1 for row in rows if row[1] == "agent_session")
        return ListExecutionGroupsResponse(
            items=items,
            total=ungrouped_total + len(rows),
            total_executions=total_executions,
            grouped_executions=total_executions - ungrouped_total,
            agent_sessions=agent_rows,
            calibration_sessions=len(rows) - agent_rows,
            skip=skip,
            limit=limit,
            children_limit=MAX_LIST_CHILDREN,
        )

    @staticmethod
    def _chip_query(
        project_id: str, chip_id: str, window: tuple[datetime, datetime] | None
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"project_id": project_id, "chip_id": chip_id}
        if window is not None:
            query["start_at"] = {"$gte": window[0], "$lt": window[1]}
        return query

    def _page_items(
        self,
        project_id: str,
        page: list[tuple[str, str, datetime | None]],
        links: ChipLinks,
        calib: ChipCalibrationGroups,
        in_window: Any,
    ) -> list[ExecutionGroupItem]:
        """Rows of one page, with batched reads for every session on it."""
        cs_ids = [key for kind, key, _ in page if kind == "calibration_session"]
        shown_runs = {cs_id: calib.runs.get(cs_id, [])[-MAX_LIST_RUNS:] for cs_id in cs_ids}
        shown_agents = {
            cs_id: calib.agents.get(cs_id, [])[-MAX_LIST_AGENT_SESSIONS:] for cs_id in cs_ids
        }
        session_ids = [key for kind, key, _ in page if kind == "agent_session"] + [
            agent_id for agents in shown_agents.values() for agent_id in agents
        ]
        child_links = {
            session_id: links.by_session.get(session_id, [])[-MAX_LIST_CHILDREN:]
            for session_id in session_ids
        }
        run_children = {
            str(run["run_id"]): calib.run_executions.get(str(run["run_id"]), [])[
                -MAX_LIST_CHILDREN:
            ]
            for runs in shown_runs.values()
            for run in runs
        }
        execution_ids = (
            [key for kind, key, _ in page if kind == "execution"]
            + [link.execution_id for shown in child_links.values() for link in shown]
            + [e.execution_id for shown in run_children.values() for e in shown]
        )
        executions = {
            doc.execution_id: doc
            for doc in cast(
                "list[ExecutionHistoryDocument]",
                ExecutionHistoryDocument.find(
                    {"project_id": project_id, "execution_id": {"$in": execution_ids}}
                ).run(),
            )
        }
        sessions: dict[str, AgentSessionDocument] = {}
        actions: dict[str, list[AgentActionDocument]] = {}
        open_interventions: Counter[str] = Counter()
        decisions: Counter[str] = Counter()
        if session_ids:
            scope = {"project_id": project_id, "session_id": {"$in": session_ids}}
            for session in cast(
                "list[AgentSessionDocument]", AgentSessionDocument.find(scope).run()
            ):
                sessions[session.session_id] = session
            for action in cast("list[AgentActionDocument]", AgentActionDocument.find(scope).run()):
                actions.setdefault(action.session_id, []).append(action)
            for session in sessions.values():
                # Actions counted by the session but not written to their collection yet.
                actions[session.session_id] = _with_pending(
                    session, actions.get(session.session_id, [])
                )
            for doc in AgentInterventionDocument.get_motor_collection().find(
                {**scope, "status": {"$in": sorted(UNANSWERED_INTERVENTION_STATUSES)}},
                {"_id": 0, "session_id": 1},
            ):
                open_interventions[str(doc["session_id"])] += 1
            for doc in AgentDecisionDocument.get_motor_collection().find(
                scope, {"_id": 0, "session_id": 1}
            ):
                decisions[str(doc["session_id"])] += 1
        # Every agent session of every calibration session row, for the targets and counts.
        all_nested = sorted(
            {agent_id for cs_id in cs_ids for agent_id in calib.agents.get(cs_id, [])}
            - set(sessions)
        )
        nested_qids: dict[str, list[str]] = {
            s.session_id: list(s.policy.qids) for s in sessions.values()
        }
        if all_nested:
            for doc in AgentSessionDocument.get_motor_collection().find(
                {"project_id": project_id, "session_id": {"$in": all_nested}},
                {"_id": 0, "session_id": 1, "policy.qids": 1},
            ):
                nested_qids[str(doc["session_id"])] = [
                    str(q) for q in (doc.get("policy") or {}).get("qids") or []
                ]
        cs_decisions = self._calibration_decisions(project_id, cs_ids)

        # Calibration sessions and reported origins of every execution on the page, and the
        # calibration session of every agent session row, each in batched reads.
        relations = resolve_execution_relations(
            project_id,
            executions.values(),
            {key: summary_link(links, key) for key in executions},
        )
        parents = agent_session_parents(project_id, sessions.values())

        def summary_of(execution_id: str) -> ExecutionResponseSummary | None:
            execution = executions.get(execution_id)
            if execution is None:
                return None
            return execution_summary(
                execution,
                summary_link(links, execution_id),
                relations.get(execution_id, NO_RELATIONS),
            )

        def agent_group(key: str) -> CalibrationGroupAgentSession | None:
            group_session = sessions.get(key)
            if group_session is None:
                return None
            session_actions = actions.get(key, [])
            all_links = links.by_session.get(key, [])
            numbers = _measurement_numbers(session_actions, links.unlinked)
            by_action = {a.action_id: a for a in session_actions}
            children: list[AgentSessionChildExecution] = []
            for link in child_links.get(key, []):
                summary = summary_of(link.execution_id)
                if summary is None:
                    continue
                child_action = by_action.get(link.action_id)
                sequence, attempt = numbers.get(link.action_id, (0, 0))
                children.append(
                    AgentSessionChildExecution(
                        action_id=link.action_id,
                        sequence=sequence,
                        attempt=attempt,
                        task_name=child_action.task_name if child_action else None,
                        qid=(
                            child_action.qids[0]
                            if child_action and len(child_action.qids) == 1
                            else None
                        ),
                        in_filter=in_window(link.start_at),
                        execution=summary,
                    )
                )
            return CalibrationGroupAgentSession(
                agent_session=_session_summary(
                    group_session,
                    actions=session_actions,
                    links=all_links,
                    unlinked=links.unlinked,
                    open_interventions=open_interventions[key],
                    decisions=decisions[key],
                    calibration_session=parents.get(key),
                ),
                children=children,
                children_total=len(all_links),
                children_in_filter=sum(1 for link in all_links if in_window(link.start_at)),
                children_omitted=max(0, len(all_links) - len(child_links.get(key, []))),
            )

        items: list[ExecutionGroupItem] = []
        for kind, key, sort_at in page:
            if kind == "execution":
                summary = summary_of(key)
                if summary is not None:
                    items.append(
                        ExecutionGroupItem(kind="execution", sort_at=sort_at, execution=summary)
                    )
                continue
            if kind == "agent_session":
                group = agent_group(key)
                if group is None:
                    continue
                items.append(
                    ExecutionGroupItem(
                        kind="agent_session",
                        sort_at=sort_at,
                        agent_session=group.agent_session,
                        children=group.children,
                        children_total=group.children_total,
                        children_in_filter=group.children_in_filter,
                        children_omitted=group.children_omitted,
                    )
                )
                continue
            items.append(
                self._calibration_item(
                    key,
                    sort_at,
                    project_id=project_id,
                    links=links,
                    calib=calib,
                    in_window=in_window,
                    shown_runs=shown_runs[key],
                    run_children=run_children,
                    nested=[
                        group
                        for agent_id in shown_agents[key]
                        if (group := agent_group(agent_id)) is not None
                    ],
                    nested_qids=nested_qids,
                    decision_docs=cs_decisions.get(key, []),
                    summary_of=summary_of,
                )
            )
        return items

    @staticmethod
    def _calibration_decisions(
        project_id: str, cs_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Decisions of the page's calibration sessions, oldest first, in one query."""
        found: dict[str, list[dict[str, Any]]] = {}
        if not cs_ids:
            return found
        for doc in (
            CalibrationDecisionDocument.get_motor_collection()
            .find(
                {"project_id": project_id, "calibration_session_id": {"$in": cs_ids}},
                {
                    "_id": 0,
                    "decision_id": 1,
                    "calibration_session_id": 1,
                    "recorded_at": 1,
                    "quota_slot": 1,
                    "conclusion": 1,
                    "supersedes_decision_id": 1,
                    "experiment.target": 1,
                },
            )
            .sort([("recorded_at", 1), ("quota_slot", 1)])
        ):
            found.setdefault(str(doc["calibration_session_id"]), []).append(doc)
        return found

    @staticmethod
    def _calibration_item(
        key: str,
        sort_at: datetime | None,
        *,
        project_id: str,
        links: ChipLinks,
        calib: ChipCalibrationGroups,
        in_window: Any,
        shown_runs: list[dict[str, Any]],
        run_children: dict[str, list[RunExecution]],
        nested: list[CalibrationGroupAgentSession],
        nested_qids: dict[str, list[str]],
        decision_docs: list[dict[str, Any]],
        summary_of: Any,
    ) -> ExecutionGroupItem:
        """A calibration session row: its summary, latest runs, and nested agent sessions."""
        doc = calib.sessions[key]
        runs = calib.runs.get(key, [])
        agents = calib.agents.get(key, [])
        statuses: list[str] = []
        moments: list[datetime] = []
        in_filter = 0
        for run in runs:
            for e in calib.run_executions.get(str(run["run_id"]), []):
                statuses.append(e.status)
                moments += [m for m in (e.start_at, e.end_at) if m is not None]
                in_filter += 1 if in_window(e.start_at) else 0
        for agent_id in agents:
            moments.append(links.session_created[agent_id])
            for link in links.by_session.get(agent_id, []):
                statuses.append(link.status)
                if link.start_at is not None:
                    moments.append(link.start_at)
                in_filter += 1 if in_window(link.start_at) else 0
        created = utc(doc.get("created_at")) or _EPOCH
        targets: set[str] = set()
        for run in runs:
            targets.update(run_target_qids(run))
        for agent_id in agents:
            targets.update(nested_qids.get(agent_id, []))
        superseded = {d.get("supersedes_decision_id") for d in decision_docs}
        for decision in decision_docs:
            target = (decision.get("experiment") or {}).get("target")
            if target:
                targets.add(str(target))
        concluded = [
            d for d in decision_docs if d.get("conclusion") and d["decision_id"] not in superseded
        ]
        recommendation = None
        if concluded:
            latest = concluded[-1]
            recommendation = CalibrationRecommendationRef(
                decision_id=str(latest["decision_id"]),
                outcome=str(latest["conclusion"].get("outcome")),
                recommended_candidate_id=latest["conclusion"].get("recommended_candidate_id"),
                recorded_at=cast("datetime", utc(latest.get("recorded_at"))),
            )
        status_value = str(doc.get("status") or "open")
        summary = CalibrationSessionGroupSummary(
            calibration_session_id=key,
            project_id=project_id,
            chip_id=str(doc["chip_id"]),
            objective=str(doc.get("objective") or ""),
            status=CalibrationSessionStatus(status_value),
            created_by=str(doc.get("created_by") or ""),
            created_at=created,
            closed_at=utc(doc.get("closed_at")),
            targets=sorted(targets, key=_target_key),
            counts=CalibrationGroupCounts(
                pipeline_runs=len(runs),
                agent_sessions=len(agents),
                executions=len(statuses),
                executions_in_filter=in_filter,
                running=sum(1 for value in statuses if value in OPEN_EXECUTION_STATUSES),
                failed=sum(1 for value in statuses if value == "failed"),
                unknown_dispatch=sum(1 for run in runs if _run_dispatch(run) == "unknown"),
                decisions=len(decision_docs),
            ),
            first_activity_at=min([created, *moments]),
            latest_activity_at=max([created, *moments]),
            recommendation=recommendation,
        )
        pipeline_runs: list[CalibrationGroupPipelineRun] = []
        for run in shown_runs:
            run_id = str(run["run_id"])
            all_executions = calib.run_executions.get(run_id, [])
            pipeline_runs.append(
                CalibrationGroupPipelineRun(
                    run_id=run_id,
                    pipeline_name=str(run.get("pipeline_name") or ""),
                    dispatch_status=_run_dispatch(run),
                    requested_by=str(run.get("requested_by") or ""),
                    requested_at=cast("datetime", utc(run.get("requested_at"))),
                    decision_id=run.get("decision_id"),
                    targets=run_target_qids(run),
                    executions=[
                        step
                        for e in run_children.get(run_id, [])
                        if (step := summary_of(e.execution_id)) is not None
                    ],
                    executions_total=len(all_executions),
                    executions_in_filter=sum(1 for e in all_executions if in_window(e.start_at)),
                )
            )
        return ExecutionGroupItem(
            kind="calibration_session",
            sort_at=sort_at,
            calibration_session=summary,
            pipeline_runs=pipeline_runs,
            pipeline_runs_omitted=max(0, len(runs) - len(shown_runs)),
            nested_agent_sessions=nested,
            nested_agent_sessions_omitted=max(0, len(agents) - len(nested)),
        )

    # ------------------------------------------------------------------ graph

    def get_session_graph(self, *, project_id: str, session_id: str) -> AgentSessionGraphResponse:
        """The session's measurements, proposals, decisions, and interventions as a graph.

        The session is read in the caller's project only, so another project's session is
        not found. Only executions on the session's chip count as its measurements, and an
        action holds an execution only as the grouped list resolves it
        (``agent_execution_links``).

        The read writes nothing. A session past its expiry is shown with ``status`` expired
        and its ``stored_status``; records the session counted but has not written yet are
        shown from its pending payload and named in ``missing``. Writing them, and recording
        the expiry, stay with the session's own load on its next operation.
        """
        records = _SessionGraphRecords.read(project_id, session_id)
        session = records.session
        actions = records.actions
        numbers = _measurement_numbers(actions, records.unlinked)
        executions = records.executions
        links = records.links

        latest_evaluation: dict[str, EvaluationDocument] = {
            evaluation.task_id: evaluation for evaluation in records.evaluations
        }
        task_of_evaluation = {e.evaluation_id: e.task_id for e in records.evaluations}
        wrong_chip = records.wrong_chip

        nodes: list[AgentSessionGraphNode] = []
        task_node: dict[str, str] = {}
        for action in actions:
            node_id = f"action:{action.action_id}"
            qid = action.qids[0] if len(action.qids) == 1 else None
            target = f"{action.task_name or action.action_type.value} on {', '.join(action.qids)}"
            if action.decision == AgentActionDecision.REJECTED:
                nodes.append(
                    AgentSessionGraphNode(
                        node_id=node_id,
                        kind="proposal",
                        order=0,
                        at=cast("datetime", utc(action.created_at)),
                        label=f"Rejected: {target}",
                        status="rejected",
                        model=action.metadata.get("model"),
                        proposal=AgentSessionGraphProposal(
                            action_id=action.action_id,
                            action_type=action.action_type.value,
                            task_name=action.task_name,
                            qids=list(action.qids),
                            reason=_text(action.reason),
                            intent=_text(action.diagnosis),
                        ),
                    )
                )
                continue
            if action.action_type != AgentActionType.RUN_TASK:
                nodes.append(
                    AgentSessionGraphNode(
                        node_id=node_id,
                        kind="session_action",
                        order=0,
                        at=cast("datetime", utc(action.created_at)),
                        label=(
                            "Asked for an expert"
                            if action.action_type == AgentActionType.REQUEST_HUMAN
                            else "Completed the session"
                        ),
                        status=action.decision.value,
                        model=action.metadata.get("model"),
                        session_action=AgentSessionGraphSessionAction(
                            action_id=action.action_id,
                            action_type=action.action_type.value,
                            reason=_text(action.reason),
                        ),
                    )
                )
                continue
            execution = executions.get(action.action_id)
            result = records.task_results.get(action.action_id) if execution else None
            conflict = records.unlinked.get(action.action_id)
            missing: list[str] = []
            if action.action_id in records.pending_action_ids:
                missing.append("action_record")
            if conflict is not None:
                missing.append(f"execution_link_{conflict.reason}")
            elif action.action_id in wrong_chip:
                missing.append("execution_on_session_chip")
            elif execution is None and _dispatched(action):
                missing.append("execution")
            if (
                execution is not None
                and result is None
                and execution.status
                in {
                    "completed",
                    "failed",
                }
            ):
                missing.append("task_result")
            evaluation = latest_evaluation.get(result.task_id) if result is not None else None
            sequence, attempt = numbers.get(action.action_id, (None, None))
            if conflict is not None:
                # Dispatched by its own record, but no execution can be attributed to it.
                status = f"link_{conflict.reason}"
            elif execution is not None:
                status = execution.status
            else:
                status = action.execution_status
            if result is not None:
                task_node[result.task_id] = node_id
            nodes.append(
                AgentSessionGraphNode(
                    node_id=node_id,
                    kind="measurement",
                    order=0,
                    at=cast(
                        "datetime",
                        utc(
                            action.dispatch_reserved_at
                            or (execution.start_at if execution else None)
                            or action.created_at
                        ),
                    ),
                    label=target if attempt in (None, 1) else f"{target} (attempt {attempt})",
                    status=status,
                    status_is_current=True,
                    model=action.metadata.get("model"),
                    missing=missing,
                    measurement=AgentSessionGraphMeasurement(
                        action_id=action.action_id,
                        task_name=action.task_name,
                        qid=qid,
                        sequence=sequence,
                        attempt=attempt,
                        repeat_of_action_id=action.metadata.get("repeat_of_action_id"),
                        dispatch_status=action.execution_status,
                        execution_id=execution.execution_id if execution else None,
                        execution_status=execution.status if execution else None,
                        task_id=result.task_id if result else None,
                        task_status=result.status if result else None,
                        started_at=utc(execution.start_at) if execution else None,
                        finished_at=utc(execution.end_at) if execution else None,
                        figure_count=len(result.figure_path) if result else 0,
                        evaluation_id=evaluation.evaluation_id if evaluation else None,
                        evaluation_status=evaluation.status if evaluation else None,
                        intent=_text(action.diagnosis),
                    ),
                )
            )

        superseded_by = {
            d.supersedes_decision_id: d.decision_id
            for d in records.decisions
            if d.supersedes_decision_id
        }
        for decision in records.decisions:
            assessment = decision.assessment.value if decision.assessment else None
            nodes.append(
                AgentSessionGraphNode(
                    node_id=f"decision:{decision.decision_id}",
                    kind="decision",
                    order=0,
                    at=cast("datetime", utc(decision.recorded_at)),
                    label=f"{assessment or 'not stated'} → {decision.next_action.value}",
                    status="superseded" if decision.decision_id in superseded_by else "recorded",
                    model=decision.model,
                    missing=[] if assessment else ["assessment"],
                    decision=AgentSessionGraphDecision(
                        decision_id=decision.decision_id,
                        assessment=assessment,
                        interpretation=_text(decision.interpretation),
                        next_action=decision.next_action.value,
                        next_detail=_text(decision.next_detail),
                        evidence_action_ids=list(decision.evidence_action_ids),
                        evaluation_ids=list(decision.evaluation_ids),
                        next_action_id=decision.next_action_id,
                        superseded_by_decision_id=superseded_by.get(decision.decision_id),
                        supersedes_decision_id=decision.supersedes_decision_id,
                    ),
                )
            )

        for item in sorted(records.interventions, key=lambda i: utc(i.created_at) or _EPOCH):
            response = item.response
            nodes.append(
                AgentSessionGraphNode(
                    node_id=f"intervention:{item.intervention_id}",
                    kind="intervention",
                    order=0,
                    at=cast("datetime", utc(item.created_at)),
                    label=f"Expert asked: {_text(item.question, 120)}",
                    status=item.status.value,
                    status_is_current=True,
                    model=item.model,
                    intervention=AgentSessionGraphIntervention(
                        intervention_id=item.intervention_id,
                        reason=item.reason.value,
                        status=item.status.value,
                        question=_text(item.question),
                        summary=_text(item.summary),
                        pauses_session=item.pauses_session,
                        response_decision=response.decision.value if response else None,
                        response_guidance=_text(response.guidance) if response else "",
                        responded_by=response.responded_by if response else None,
                        responded_at=utc(response.responded_at) if response else None,
                        resumed_at=utc(item.resumed_at),
                        resume_outcome=(
                            item.resume_outcome.transition if item.resume_outcome else None
                        ),
                    ),
                )
            )

        rank = {"proposal": 0, "measurement": 0, "session_action": 0, "decision": 1}
        nodes.sort(
            key=lambda n: (
                n.at.isoformat(timespec="milliseconds"),
                rank.get(n.kind, 2),
                n.node_id,
            )
        )
        for index, node in enumerate(nodes):
            node.order = index

        edges = self._edges(nodes, records, task_node, task_of_evaluation)
        omitted = max(0, len(nodes) - MAX_SESSION_GRAPH_NODES)
        kept = nodes[omitted:]
        kept_ids = {node.node_id for node in kept}
        open_count = sum(
            1
            for item in records.interventions
            if item.status.value in UNANSWERED_INTERVENTION_STATUSES
        )
        return AgentSessionGraphResponse(
            generated_at=cast("datetime", utc(now())),
            session=_session_summary(
                session,
                actions=actions,
                links=links,
                unlinked=records.unlinked,
                open_interventions=open_count,
                decisions=len(records.decisions),
            ),
            nodes=kept,
            edges=[e for e in edges if e.source in kept_ids and e.target in kept_ids],
            total_nodes=len(nodes),
            omitted_nodes=omitted,
            complete=omitted == 0,
            notes=SESSION_GRAPH_NOTES,
        )

    @staticmethod
    def _edges(
        nodes: list[AgentSessionGraphNode],
        records: _SessionGraphRecords,
        task_node: dict[str, str],
        task_of_evaluation: dict[str, str],
    ) -> list[AgentSessionGraphEdge]:
        """Typed edges: temporal sequence, and links named by the records."""
        known = {node.node_id for node in nodes}
        edges: dict[str, AgentSessionGraphEdge] = {}

        def add(kind: AgentSessionGraphEdgeKind, source: str, target: str) -> bool:
            if source not in known or target not in known or source == target:
                return False
            edge_id = f"{kind}:{source}->{target}"
            edges.setdefault(
                edge_id,
                AgentSessionGraphEdge(edge_id=edge_id, kind=kind, source=source, target=target),
            )
            return True

        dispatched = sorted(
            (
                node
                for node in nodes
                if node.measurement is not None and node.measurement.sequence is not None
            ),
            key=lambda node: cast("AgentSessionGraphMeasurement", node.measurement).sequence or 0,
        )
        for previous, current in pairwise(dispatched):
            add("sequence", previous.node_id, current.node_id)

        for node in nodes:
            if node.measurement is not None and node.measurement.repeat_of_action_id:
                add("retry_of", f"action:{node.measurement.repeat_of_action_id}", node.node_id)

        by_id = {node.node_id: node for node in nodes}
        for decision in records.decisions:
            node_id = f"decision:{decision.decision_id}"
            node = by_id[node_id]
            for action_id in decision.evidence_action_ids:
                if not add("evidence", f"action:{action_id}", node_id):
                    node.missing.append(f"evidence action {action_id}")
            for evaluation_id in decision.evaluation_ids:
                task_id = task_of_evaluation.get(evaluation_id)
                source = task_node.get(task_id) if task_id else None
                if source is None or not add("evidence", source, node_id):
                    node.missing.append(f"evidence evaluation {evaluation_id}")
            if decision.next_action_id:
                add("next_action", node_id, f"action:{decision.next_action_id}")
            if decision.intervention_id:
                add("escalation", node_id, f"intervention:{decision.intervention_id}")
            node.missing = node.missing[:MAX_MISSING]

        for item in records.interventions:
            target = f"intervention:{item.intervention_id}"
            if item.action_id:
                add("escalation", f"action:{item.action_id}", target)
            if item.previous_intervention_id:
                add("follow_up", f"intervention:{item.previous_intervention_id}", target)
            if item.resume_outcome and item.resume_outcome.follow_up_intervention_id:
                add(
                    "follow_up",
                    target,
                    f"intervention:{item.resume_outcome.follow_up_intervention_id}",
                )
        return list(edges.values())
