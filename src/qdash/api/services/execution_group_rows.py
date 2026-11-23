"""Rows of one page of the grouped Execution list, assembled with batched reads.

The page is already cut (``execution_group_list``): each entry names an execution, an agent
session, or a calibration session row. This module reads only what those rows show — the
executions, the agent sessions and their counts, and the calibration sessions' decisions — and
builds the response items. Membership and order are never decided here, and nothing is written.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from qdash.api.schemas.execution_group import (
    AgentSessionChildExecution,
    CalibrationGroupAgentSession,
    CalibrationGroupCounts,
    CalibrationGroupPipelineRun,
    CalibrationRecommendationRef,
    CalibrationSessionGroupSummary,
    ExecutionGroupItem,
)
from qdash.api.services.agent_execution_links import (
    OPEN_EXECUTION_STATUSES,
    ChipLinks,
    summary_link,
    utc,
)
from qdash.api.services.agent_session_group_summary import (
    EPOCH,
    UNANSWERED_INTERVENTION_STATUSES,
    measurement_numbers,
    session_summary,
    with_pending,
)
from qdash.api.services.calibration_session_links import (
    NO_RELATIONS,
    agent_session_parents,
    resolve_execution_relations,
)
from qdash.api.services.execution_service import execution_summary
from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import (
    CalibrationRunKind,
    CalibrationRunTrigger,
    CalibrationSessionOrigin,
    CalibrationSessionStatus,
)
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentDecisionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.calibration_session import CalibrationDecisionDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument

if TYPE_CHECKING:
    from qdash.api.schemas.execution import ExecutionResponseSummary
    from qdash.api.services.calibration_session_groups import ChipCalibrationGroups, RunExecution

# Executions one session row of the list carries; the graph lists every one.
MAX_LIST_CHILDREN = 20
# Pipeline runs and nested agent sessions one calibration session row carries.
MAX_LIST_RUNS = 20
MAX_LIST_AGENT_SESSIONS = 20

# One entry of a cut page: row kind, row key, and the moment the row is ordered by.
PageEntry = tuple[str, str, datetime | None]


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


def page_items(
    project_id: str,
    page: list[PageEntry],
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
        str(run["run_id"]): calib.run_executions.get(str(run["run_id"]), [])[-MAX_LIST_CHILDREN:]
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
        for session in cast("list[AgentSessionDocument]", AgentSessionDocument.find(scope).run()):
            sessions[session.session_id] = session
        for action in cast("list[AgentActionDocument]", AgentActionDocument.find(scope).run()):
            actions.setdefault(action.session_id, []).append(action)
        for session in sessions.values():
            # Actions counted by the session but not written to their collection yet.
            actions[session.session_id] = with_pending(session, actions.get(session.session_id, []))
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
        {agent_id for cs_id in cs_ids for agent_id in calib.agents.get(cs_id, [])} - set(sessions)
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
    cs_decisions = _calibration_decisions(project_id, cs_ids)

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
        numbers = measurement_numbers(session_actions, links.unlinked)
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
            agent_session=session_summary(
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
            _calibration_item(
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


def _calibration_decisions(project_id: str, cs_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
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
    created = utc(doc.get("created_at")) or EPOCH
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
        origin=CalibrationSessionOrigin(
            str(doc.get("origin") or CalibrationSessionOrigin.MANUAL.value)
        ),
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
                run_kind=CalibrationRunKind(
                    str(run.get("run_kind") or CalibrationRunKind.PIPELINE.value)
                ),
                run_name=str(run.get("run_name") or run.get("pipeline_name") or ""),
                trigger=CalibrationRunTrigger(
                    str(run.get("trigger") or CalibrationRunTrigger.API.value)
                ),
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
