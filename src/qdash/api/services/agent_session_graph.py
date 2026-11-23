"""One agent session's graph over its executions: measurements, proposals, decisions, and
interventions as typed nodes, with temporal sequence edges and edges the records name.

A read-only projection. An action holds an execution only as the grouped Execution list
resolves it (``agent_execution_links``), on the session's chip and in the caller's project, so
the two views never disagree about which execution a measurement is.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING, Any, cast

from bunnet import SortDirection
from fastapi import HTTPException

from qdash.api.schemas.execution_group import (
    AgentSessionGraphDecision,
    AgentSessionGraphEdge,
    AgentSessionGraphEdgeKind,
    AgentSessionGraphIntervention,
    AgentSessionGraphMeasurement,
    AgentSessionGraphNode,
    AgentSessionGraphProposal,
    AgentSessionGraphResponse,
    AgentSessionGraphSessionAction,
)
from qdash.api.services.agent_execution_links import (
    ExecutionLink,
    UnlinkedAction,
    keys_on_other_chips,
    resolve_chip_links,
    utc,
)
from qdash.api.services.agent_session_group_summary import (
    EPOCH,
    MAX_MISSING,
    UNANSWERED_INTERVENTION_STATUSES,
    action_key,
    is_dispatched,
    is_measurement,
    measurement_numbers,
    session_summary,
    with_pending,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentActionDecision, AgentActionType
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentDecisionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from datetime import datetime

# Nodes one graph response carries; the latest are kept and the audit holds the rest.
MAX_SESSION_GRAPH_NODES = 1000
MAX_TEXT = 500

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


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class SessionGraphRecords:
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
    def read(cls, project_id: str, session_id: str) -> SessionGraphRecords:
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
        actions = sorted(with_pending(session, stored), key=action_key)
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
            if is_measurement(a)
            and is_dispatched(a)
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


def build_session_graph(*, project_id: str, session_id: str) -> AgentSessionGraphResponse:
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
    records = SessionGraphRecords.read(project_id, session_id)
    session = records.session
    actions = records.actions
    numbers = measurement_numbers(actions, records.unlinked)
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
        elif execution is None and is_dispatched(action):
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

    for item in sorted(records.interventions, key=lambda i: utc(i.created_at) or EPOCH):
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

    edges = _edges(nodes, records, task_node, task_of_evaluation)
    omitted = max(0, len(nodes) - MAX_SESSION_GRAPH_NODES)
    kept = nodes[omitted:]
    kept_ids = {node.node_id for node in kept}
    open_count = sum(
        1 for item in records.interventions if item.status.value in UNANSWERED_INTERVENTION_STATUSES
    )
    return AgentSessionGraphResponse(
        generated_at=cast("datetime", utc(now())),
        session=session_summary(
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


def _edges(
    nodes: list[AgentSessionGraphNode],
    records: SessionGraphRecords,
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
