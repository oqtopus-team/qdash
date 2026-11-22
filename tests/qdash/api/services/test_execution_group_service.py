"""Tests for the Execution list grouped by agent session and for a session's graph.

Groups are read from authoritative records: a session's action names the execution it
dispatched. A tag alone never groups an execution, grouping happens before pagination, and a
group's status is the session's while each child keeps its own execution's status.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import HTTPException

from qdash.api.schemas.agent_session import (
    CreateAgentInterventionRequest,
    CreateAgentSessionRequest,
    RecordAgentDecisionRequest,
    RespondAgentInterventionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_execution_links import link_for_execution
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_session_audit import AgentSessionAuditService
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.api.services.execution_group_service import (
    MAX_LIST_CHILDREN,
    ExecutionGroupService,
)
from qdash.api.services.execution_service import ExecutionService
from qdash.datamodel.agent_session import (
    AgentActionType,
    AgentAutonomy,
    AgentModelIdentity,
    AgentSessionPolicy,
    AgentSessionStatus,
)
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.execution_history import MongoExecutionHistoryRepository
from qdash.repository.execution_lock import MongoExecutionLockRepository

if TYPE_CHECKING:
    from qdash.api.schemas.execution_group import (
        AgentSessionGraphIntervention,
        AgentSessionGraphMeasurement,
        AgentSessionGraphNode,
        AgentSessionGraphResponse,
        AgentSessionGroupSummary,
        ExecutionGroupItem,
        ListExecutionGroupsResponse,
    )

PROJECT = "project-1"
OTHER = "project-2"
OWNER = "alice"
CHIP = "chip-001"
BASE = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)


@pytest.fixture
def sessions(init_db) -> AgentSessionService:
    for project_id in (PROJECT, OTHER):
        for chip_id in (CHIP, "chip-002"):
            ChipDocument(
                project_id=project_id,
                chip_id=chip_id,
                username=OWNER,
                size=4,
                system_info=SystemInfoModel(),
            ).insert()
    QubitDocument(
        project_id=PROJECT,
        username=OWNER,
        qid="Q00",
        chip_id=CHIP,
        data={},
        system_info=SystemInfoModel(),
    ).insert()
    return AgentSessionService(intervention_service=AgentInterventionService())


@pytest.fixture
def groups() -> ExecutionGroupService:
    return ExecutionGroupService(execution_history_repository=MongoExecutionHistoryRepository())


def _session(sessions: AgentSessionService, *, project_id: str = PROJECT, chip_id: str = CHIP):
    return sessions.create_session(
        project_id=project_id,
        username=OWNER,
        body=CreateAgentSessionRequest(
            chip_id=chip_id,
            policy=AgentSessionPolicy(
                qids=["Q00"],
                allowed_tasks=["CheckQubitFrequency", "CheckRabi"],
                autonomy=AgentAutonomy.AUTO,
                max_actions=50,
                max_rounds_per_target=20,
            ),
        ),
    )


def _set_created(session_id: str, at: datetime) -> None:
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session_id}, {"$set": {"created_at": at}}
    )


def _submit(
    sessions: AgentSessionService,
    session_id: str,
    *,
    key: str,
    task: str = "CheckQubitFrequency",
    project_id: str = PROJECT,
    repeat_of: str | None = None,
):
    version = sessions.get_session(project_id=project_id, session_id=session_id).state_version
    submitted = sessions.submit_action(
        project_id=project_id,
        session_id=session_id,
        username=OWNER,
        body=SubmitAgentActionRequest(
            idempotency_key=key,
            expected_state_version=version,
            action_type=AgentActionType.RUN_TASK,
            task_name=task,
            qids=["Q00"],
            diagnosis=f"Measure {task}.",
        ),
    )
    if repeat_of:
        # As an autonomous repeat records it; the gate checks of autonomy are tested elsewhere.
        AgentActionDocument.get_motor_collection().update_one(
            {"action_id": submitted.action_id},
            {"$set": {"metadata.repeat_of_action_id": repeat_of}},
        )
    return submitted


def _execution(
    execution_id: str,
    *,
    start: datetime,
    project_id: str = PROJECT,
    chip_id: str = CHIP,
    status: str = "completed",
    tags: list[str] | None = None,
    flow_run_id: str | None = None,
    name: str = "manual",
) -> None:
    ExecutionHistoryDocument(
        project_id=project_id,
        username=OWNER,
        name=name,
        execution_id=execution_id,
        calib_data_path="",
        note={"flow_run_id": flow_run_id} if flow_run_id else {},
        status=status,
        tags=tags or [],
        chip_id=chip_id,
        start_at=start,
        end_at=start + timedelta(seconds=5),
        message="",
        system_info=SystemInfoModel(),
    ).insert()


def _dispatch(
    session_id: str,
    action_id: str,
    *,
    sequence: int,
    start: datetime,
    status: str = "completed",
    task: str = "CheckQubitFrequency",
    project_id: str = PROJECT,
    chip_id: str = CHIP,
    with_result: bool = True,
) -> str:
    """Give an action its real execution and task result, as dispatch and the worker would."""
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": action_id},
        {
            "$set": {
                "operation_id": f"flow-{sequence}",
                "execution_status": "queued",
                "dispatch_reserved_at": start,
            }
        },
    )
    _execution(
        f"agent-exec-{sequence}",
        start=start,
        project_id=project_id,
        chip_id=chip_id,
        status=status,
        tags=[f"agent-session:{session_id}"],
        flow_run_id=f"flow-{sequence}",
        name=f"agent:{task}",
    )
    task_id = f"task-{sequence}"
    if with_result:
        TaskResultHistoryDocument(
            project_id=project_id,
            username=OWNER,
            task_id=task_id,
            name=task,
            upstream_id="",
            status=status,
            message="",
            input_parameters={},
            output_parameters={},
            output_parameter_names=[],
            run_parameters={},
            note={},
            figure_path=["/data/fig.png"],
            json_figure_path=[],
            raw_data_path=[],
            start_at=start,
            end_at=start + timedelta(seconds=5),
            elapsed_time=5.0,
            task_type="qubit",
            system_info=SystemInfoModel(),
            qid="Q00",
            execution_id=f"agent-exec-{sequence}",
            tags=[],
            chip_id=chip_id,
        ).insert()
    return task_id


def _decide(session_id: str, key: str, **fields: Any):
    return AgentSessionAuditService().record_decision(
        project_id=PROJECT,
        session_id=session_id,
        username=OWNER,
        body=RecordAgentDecisionRequest.model_validate(
            {
                "idempotency_key": key,
                "assessment": "pass",
                "interpretation": "Both peaks agree within 1 MHz.",
                "next_action": "next_task",
                **fields,
            }
        ),
    )


def _summary(item: ExecutionGroupItem) -> AgentSessionGroupSummary:
    assert item.agent_session is not None
    return item.agent_session


def _measured(node: AgentSessionGraphNode) -> AgentSessionGraphMeasurement:
    assert node.measurement is not None
    return node.measurement


def _asked(node: AgentSessionGraphNode) -> AgentSessionGraphIntervention:
    assert node.intervention is not None
    return node.intervention


def _execution_doc(execution_id: str) -> ExecutionHistoryDocument:
    doc = ExecutionHistoryDocument.find_one({"execution_id": execution_id}).run()
    assert doc is not None
    return doc


def _rows(result) -> list[str]:
    return [
        item.execution.execution_id
        if item.kind == "execution"
        else f"S:{_summary(item).session_id}"
        for item in result.items
    ]


def test_mixed_list_groups_before_pagination_without_duplicates(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    """Ordinary, pipeline, and agent executions share one newest-first order across pages."""
    session = _session(sessions)
    _set_created(session.session_id, BASE + timedelta(minutes=5))
    _execution("manual-1", start=BASE + timedelta(minutes=1))
    _execution(
        "pipe-1", start=BASE + timedelta(minutes=2), flow_run_id="pipe-flow", name="pipeline"
    )
    _execution(
        "pipe-2", start=BASE + timedelta(minutes=3), flow_run_id="pipe-flow", name="pipeline"
    )
    first = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, first.action_id, sequence=1, start=BASE + timedelta(minutes=6))
    _execution("manual-2", start=BASE + timedelta(minutes=7))
    second = _submit(sessions, session.session_id, key="a-2")
    _dispatch(session.session_id, second.action_id, sequence=2, start=BASE + timedelta(minutes=8))
    _execution("manual-3", start=BASE + timedelta(minutes=9))

    whole = groups.list_groups(project_id=PROJECT, chip_id=CHIP, skip=0, limit=100)
    # The session sits where its latest measurement started.
    assert _rows(whole) == [
        "manual-3",
        f"S:{session.session_id}",
        "manual-2",
        "pipe-2",
        "pipe-1",
        "manual-1",
    ]
    assert whole.total == 6
    assert whole.total_executions == 7
    assert whole.grouped_executions == 2
    assert whole.agent_sessions == 1
    group = whole.items[1]
    assert [c.execution.execution_id for c in group.children] == ["agent-exec-1", "agent-exec-2"]
    assert [c.sequence for c in group.children] == [1, 2]
    assert [c.attempt for c in group.children] == [1, 2]
    assert group.children_total == 2

    paged: list[str] = []
    for skip in range(0, 6, 2):
        page = groups.list_groups(project_id=PROJECT, chip_id=CHIP, skip=skip, limit=2)
        assert page.total == 6
        paged.extend(_rows(page))
        for item in page.items:
            if item.kind == "agent_session":
                # The whole session is on one page.
                assert item.children_total == 2 and len(item.children) == 2
    assert paged == _rows(whole)
    assert len(set(paged)) == len(paged)

    # The ungrouped list is unchanged and still counts every execution.
    flat = ExecutionService(MongoExecutionHistoryRepository(), MongoExecutionLockRepository())
    assert flat.count_executions(project_id=PROJECT, chip_id=CHIP) == 7
    assert len(flat.list_executions(project_id=PROJECT, chip_id=CHIP, limit=100)) == 7


def test_day_filter_keeps_group_semantics_explicit(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    _set_created(session.session_id, BASE - timedelta(hours=2))
    yesterday = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, yesterday.action_id, sequence=1, start=BASE - timedelta(hours=1))
    today = _submit(sessions, session.session_id, key="a-2")
    _dispatch(session.session_id, today.action_id, sequence=2, start=BASE + timedelta(hours=3))
    _execution("manual-yesterday", start=BASE - timedelta(hours=5))
    _execution("manual-today", start=BASE + timedelta(hours=1))

    result = groups.list_groups(project_id=PROJECT, chip_id=CHIP, date="20261120", timezone="UTC")
    assert _rows(result) == [f"S:{session.session_id}", "manual-today"]
    group = result.items[0]
    assert group.children_total == 2
    assert group.children_in_filter == 1
    assert [c.in_filter for c in group.children] == [False, True]
    assert result.total_executions == 2
    assert result.grouped_executions == 1

    earlier = groups.list_groups(project_id=PROJECT, chip_id=CHIP, date="20261119", timezone="UTC")
    assert _rows(earlier) == [f"S:{session.session_id}", "manual-yesterday"]
    assert earlier.items[0].sort_at == BASE - timedelta(hours=1)

    empty = groups.list_groups(project_id=PROJECT, chip_id=CHIP, date="20261118", timezone="UTC")
    assert empty.items == [] and empty.total == 0


def test_session_without_execution_and_rejected_proposal_is_a_group(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    rejected = _submit(sessions, session.session_id, key="bad", task="NotAllowed")
    assert rejected.decision.value == "rejected"
    pending = _submit(sessions, session.session_id, key="a-1")

    result = groups.list_groups(project_id=PROJECT, chip_id=CHIP)
    assert result.total == 1 and result.total_executions == 0
    group = result.items[0]
    assert group.kind == "agent_session"
    assert group.children == []
    summary = _summary(group)
    assert summary.status == AgentSessionStatus.ACTIVE
    assert summary.counts.rejected_proposals == 1
    assert summary.counts.measurements == 0
    assert summary.counts.pending_dispatch == 1
    assert summary.counts.in_flight == 0

    graph = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    kinds = {node.node_id: node.kind for node in graph.nodes}
    assert kinds[f"action:{rejected.action_id}"] == "proposal"
    measurement = next(n for n in graph.nodes if n.node_id == f"action:{pending.action_id}")
    assert measurement.kind == "measurement"
    assert measurement.status == "not_started"
    assert _measured(measurement).execution_id is None
    assert _measured(measurement).sequence is None
    # A proposal never ran, so it carries no execution or task id.
    proposal = next(n for n in graph.nodes if n.kind == "proposal")
    assert (
        proposal.measurement is None and proposal.proposal is not None and proposal.proposal.reason
    )


def test_graph_typed_edges_retries_and_multiple_antecedents(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    first = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, first.action_id, sequence=1, start=BASE)
    retry = _submit(sessions, session.session_id, key="a-2", repeat_of=first.action_id)
    _dispatch(session.session_id, retry.action_id, sequence=2, start=BASE + timedelta(minutes=1))
    rabi = _submit(sessions, session.session_id, key="a-3", task="CheckRabi")
    _dispatch(
        session.session_id,
        rabi.action_id,
        sequence=3,
        start=BASE + timedelta(minutes=2),
        task="CheckRabi",
        status="failed",
    )
    decision = _decide(
        session.session_id,
        "d-1",
        evidence_action_ids=[first.action_id, retry.action_id],
        next_action_id=rabi.action_id,
    )

    graph = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    assert graph.complete and graph.omitted_nodes == 0
    by_id = {node.node_id: node for node in graph.nodes}
    m1, m2, m3 = (by_id[f"action:{a.action_id}"] for a in (first, retry, rabi))
    # Retries are distinct nodes with their own execution and task result.
    assert (_measured(m1).execution_id, _measured(m2).execution_id) == (
        "agent-exec-1",
        "agent-exec-2",
    )
    assert (_measured(m1).task_id, _measured(m2).task_id) == ("task-1", "task-2")
    assert (_measured(m1).attempt, _measured(m2).attempt) == (1, 2)
    assert _measured(m2).repeat_of_action_id == first.action_id
    # The child status is the real execution's.
    assert m3.status == "failed" and _measured(m3).figure_count == 1

    edges = {(edge.kind, edge.source, edge.target) for edge in graph.edges}
    d = f"decision:{decision.decision_id}"
    assert ("sequence", m1.node_id, m2.node_id) in edges
    assert ("sequence", m2.node_id, m3.node_id) in edges
    assert ("retry_of", m1.node_id, m2.node_id) in edges
    # One decision citing two prior results.
    assert ("evidence", m1.node_id, d) in edges
    assert ("evidence", m2.node_id, d) in edges
    assert ("next_action", d, m3.node_id) in edges
    # Time alone never makes a causal edge: the failed Rabi feeds no decision.
    assert not any(kind == "evidence" and src == m3.node_id for kind, src, _ in edges)
    assert all(
        edge.kind != "evidence" or edge.target.startswith("decision:") for edge in graph.edges
    )
    assert [node.order for node in graph.nodes] == list(range(len(graph.nodes)))
    assert "raw_data_path" not in graph.model_dump_json()


def test_human_wait_and_reply_status_come_from_the_session(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    first = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, first.action_id, sequence=1, start=BASE)
    opened = sessions.interventions.create_intervention(
        project_id=PROJECT,
        session_id=session.session_id,
        username=OWNER,
        body=CreateAgentInterventionRequest.model_validate(
            {
                "idempotency_key": "human-1",
                "reason": "evaluation_failed",
                "summary": "R2 is low.",
                "question": "Widen the sweep or stop?",
                "qids": ["Q00"],
                "autonomous": True,
            }
        ),
    )
    waiting = groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0]
    assert _summary(waiting).status == AgentSessionStatus.WAITING_FOR_HUMAN
    assert _summary(waiting).active_intervention_id == opened.intervention_id
    assert _summary(waiting).counts.open_interventions == 1
    assert _summary(waiting).counts.in_flight == 0
    # The finished child keeps its own status while the session waits.
    assert waiting.children[0].execution.status == "completed"

    graph = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    node = next(n for n in graph.nodes if n.kind == "intervention")
    assert node.status == "open"
    assert _asked(node).question == "Widen the sweep or stop?"
    assert node.measurement is None

    paused = sessions.get_session(project_id=PROJECT, session_id=session.session_id)
    sessions.interventions.respond(
        project_id=PROJECT,
        session_id=session.session_id,
        intervention_id=opened.intervention_id,
        username="expert",
        body=RespondAgentInterventionRequest.model_validate(
            {
                "idempotency_key": "r-1",
                "expected_state_version": paused.state_version,
                "decision": "stop",
                "guidance": "Stop here.",
            }
        ),
    )
    answered = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    node = next(n for n in answered.nodes if n.kind == "intervention")
    assert _asked(node).response_decision == "stop"
    assert _asked(node).responded_by == "expert"
    assert answered.session.status == AgentSessionStatus.CANCELLED
    listed = groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0]
    assert _summary(listed).counts.open_interventions == 0


def test_in_flight_idle_completed_and_expired(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    running = _submit(sessions, session.session_id, key="a-1")
    _dispatch(
        session.session_id,
        running.action_id,
        sequence=1,
        start=BASE,
        status="running",
        with_result=False,
    )
    summary = _summary(groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0])
    assert summary.status == AgentSessionStatus.ACTIVE
    assert summary.counts.in_flight == 1

    ExecutionHistoryDocument.get_motor_collection().update_one(
        {"execution_id": "agent-exec-1"}, {"$set": {"status": "completed"}}
    )
    summary = _summary(groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0])
    # Active and idle between measurements: not failed for holding no lock.
    assert summary.status == AgentSessionStatus.ACTIVE
    assert summary.counts.in_flight == 0

    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session.session_id},
        {"$set": {"expires_at": datetime.now(UTC) - timedelta(minutes=1)}},
    )
    summary = _summary(groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0])
    assert summary.status == AgentSessionStatus.EXPIRED
    assert summary.stored_status == AgentSessionStatus.ACTIVE

    done = _session(sessions)
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": done.session_id}, {"$set": {"status": "completed"}}
    )
    statuses = {
        _summary(item).session_id: _summary(item).status
        for item in groups.list_groups(project_id=PROJECT, chip_id=CHIP).items
    }
    assert statuses[done.session_id] == AgentSessionStatus.COMPLETED


def test_legacy_tag_without_action_link_stays_an_execution(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    _execution(
        "legacy-1",
        start=BASE,
        tags=[f"agent-session:{session.session_id}"],
        flow_run_id="legacy-flow",
    )
    _execution("orphan-1", start=BASE + timedelta(minutes=1), tags=["agent-session:gone"])
    result = groups.list_groups(project_id=PROJECT, chip_id=CHIP)
    assert "legacy-1" in _rows(result) and "orphan-1" in _rows(result)
    assert result.grouped_executions == 0
    group = next(item for item in result.items if item.kind == "agent_session")
    assert group.children == []

    legacy = _execution_doc("legacy-1")
    link = link_for_execution(PROJECT, legacy)
    assert link is not None and link.linked is False and link.session_id == session.session_id
    assert link.status == AgentSessionStatus.ACTIVE
    orphan = _execution_doc("orphan-1")
    orphan_link = link_for_execution(PROJECT, orphan)
    assert orphan_link is not None and orphan_link.status is None and not orphan_link.linked


def test_list_rows_carry_agent_attribution_only_from_action_links(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    """Flat and grouped rows attribute an execution to an agent only through its action."""
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, action.action_id, sequence=1, start=BASE)
    _execution(
        "legacy-1",
        start=BASE + timedelta(minutes=1),
        tags=[f"agent-session:{session.session_id}"],
    )
    _execution("manual-1", start=BASE + timedelta(minutes=2))

    flat = ExecutionService(MongoExecutionHistoryRepository(), MongoExecutionLockRepository())
    rows = {row.execution_id: row for row in flat.list_executions(PROJECT, CHIP, limit=100)}
    link = rows["agent-exec-1"].agent_session
    assert link is not None and link.linked and link.action_id == action.action_id
    assert link.session_id == session.session_id and link.created_by == OWNER
    assert link.status == AgentSessionStatus.ACTIVE
    # The recorded actor is kept as is.
    assert rows["agent-exec-1"].username == OWNER
    assert rows["legacy-1"].agent_session is None
    assert rows["manual-1"].agent_session is None

    grouped = groups.list_groups(project_id=PROJECT, chip_id=CHIP)
    group = next(item for item in grouped.items if item.kind == "agent_session")
    assert group.children[0].execution.agent_session == link
    for item in grouped.items:
        if item.kind == "execution":
            assert item.execution is not None and item.execution.agent_session is None

    # The detail reports the same verified link, creator included.
    detail = flat.get_execution(PROJECT, "agent-exec-1")
    assert detail is not None and detail.agent_session == link


def test_rows_and_graph_show_each_records_reported_model(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    """The session row shows the creating host's model; each graph node keeps its own."""
    created = AgentModelIdentity(provider="ollama", model_id="qwen3:32b", host="pi")
    switched = AgentModelIdentity(provider="vllm", model_id="qwen3:32b", host="qdash-web-agent")
    session = sessions.create_session(
        project_id=PROJECT,
        username=OWNER,
        body=CreateAgentSessionRequest(
            chip_id=CHIP,
            policy=AgentSessionPolicy(qids=["Q00"], allowed_tasks=["CheckQubitFrequency"]),
            model=created,
        ),
    )
    action = sessions.submit_action(
        project_id=PROJECT,
        session_id=session.session_id,
        username=OWNER,
        body=SubmitAgentActionRequest(
            idempotency_key="a-1",
            expected_state_version=0,
            action_type=AgentActionType.RUN_TASK,
            task_name="CheckQubitFrequency",
            qids=["Q00"],
            model=switched,
        ),
    )
    _dispatch(session.session_id, action.action_id, sequence=1, start=BASE)
    legacy = _submit(sessions, session.session_id, key="a-2")
    decided = _decide(session.session_id, "d-1", model=switched.model_dump())

    grouped = groups.list_groups(project_id=PROJECT, chip_id=CHIP)
    summary = _summary(_group(grouped, session.session_id))
    assert summary.model == created
    assert summary.model_name == "ollama/qwen3:32b"
    link = link_for_execution(PROJECT, _execution_doc("agent-exec-1"))
    assert link is not None and link.model_name == "ollama/qwen3:32b"

    graph = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    assert graph.session.model == created
    assert _node(graph, action.action_id).model == switched
    assert _node(graph, legacy.action_id).model is None
    decision_node = next(n for n in graph.nodes if n.node_id == f"decision:{decided.decision_id}")
    assert decision_node.model == switched


def test_link_for_execution_is_authoritative_and_chip_scoped(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, action.action_id, sequence=1, start=BASE)
    execution = _execution_doc("agent-exec-1")
    link = link_for_execution(PROJECT, execution)
    assert link is not None and link.linked and link.action_id == action.action_id

    # The detail endpoint reports the same link.
    detail = ExecutionService(
        MongoExecutionHistoryRepository(), MongoExecutionLockRepository()
    ).get_execution(PROJECT, "agent-exec-1")
    assert detail is not None and detail.agent_session is not None
    assert detail.agent_session.session_id == session.session_id

    # An operation that resolves on another chip links nothing on either chip.
    stray = _submit(sessions, session.session_id, key="a-2")
    _dispatch(session.session_id, stray.action_id, sequence=2, start=BASE, chip_id="chip-002")
    other_chip = groups.list_groups(project_id=PROJECT, chip_id="chip-002")
    assert _rows(other_chip) == ["agent-exec-2"]
    stray_exec = _execution_doc("agent-exec-2")
    stray_link = link_for_execution(PROJECT, stray_exec)
    assert stray_link is not None and not stray_link.linked
    graph = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    stray_node = next(n for n in graph.nodes if n.node_id == f"action:{stray.action_id}")
    assert _measured(stray_node).execution_id is None
    assert "execution_on_session_chip" in stray_node.missing


def test_cross_project_records_are_never_read(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    mine = _session(sessions)
    theirs = _session(sessions, project_id=OTHER)
    action = _submit(sessions, theirs.session_id, key="a-1", project_id=OTHER)
    _dispatch(theirs.session_id, action.action_id, sequence=1, start=BASE, project_id=OTHER)

    assert _rows(groups.list_groups(project_id=PROJECT, chip_id=CHIP)) == [f"S:{mine.session_id}"]
    with pytest.raises(HTTPException) as denied:
        groups.get_session_graph(project_id=PROJECT, session_id=theirs.session_id)
    assert denied.value.status_code == 404


def test_list_children_are_bounded_and_say_so(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    count = MAX_LIST_CHILDREN + 3
    for index in range(1, count + 1):
        action = _submit(sessions, session.session_id, key=f"a-{index}")
        _dispatch(
            session.session_id,
            action.action_id,
            sequence=index,
            start=BASE + timedelta(minutes=index),
            with_result=False,
        )
    group = groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0]
    assert group.children_total == count
    assert len(group.children) == MAX_LIST_CHILDREN
    assert group.children_omitted == 3
    # The latest are shown, in dispatch order.
    assert group.children[-1].sequence == count
    assert group.children[0].sequence == 4


# ---------------------------------------------------------------------- link resolution


def _node(graph: AgentSessionGraphResponse, action_id: str) -> AgentSessionGraphNode:
    return next(n for n in graph.nodes if n.node_id == f"action:{action_id}")


def _set_action(action_id: str, **fields: Any) -> None:
    AgentActionDocument.get_motor_collection().update_one(
        {"action_id": action_id}, {"$set": fields}
    )


def _group(result: ListExecutionGroupsResponse, session_id: str) -> ExecutionGroupItem:
    return next(
        item
        for item in result.items
        if item.kind == "agent_session" and _summary(item).session_id == session_id
    )


def test_two_sessions_naming_one_execution_agree_on_the_earliest_action(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    """The list, the detail, and both graphs give the execution to the same action."""
    first = _session(sessions)
    second = _session(sessions)
    early = _submit(sessions, first.session_id, key="a-1")
    late = _submit(sessions, second.session_id, key="b-1")
    _dispatch(first.session_id, early.action_id, sequence=1, start=BASE)
    _set_action(late.action_id, operation_id="flow-1", execution_status="queued")
    # Inserted first, but recorded later: the order is the records', not the database's.
    _set_action(early.action_id, created_at=BASE + timedelta(minutes=2))
    _set_action(late.action_id, created_at=BASE + timedelta(minutes=1))

    result = groups.list_groups(project_id=PROJECT, chip_id=CHIP)
    assert result.grouped_executions == 1
    winner, loser = _group(result, second.session_id), _group(result, first.session_id)
    assert [c.execution.execution_id for c in winner.children] == ["agent-exec-1"]
    assert loser.children == [] and _summary(loser).counts.measurements == 0
    assert any(
        f"held by action {late.action_id} of session {second.session_id}" in text
        for text in _summary(loser).missing
    )
    link = link_for_execution(PROJECT, _execution_doc("agent-exec-1"))
    assert link is not None and link.linked and link.action_id == late.action_id

    won = groups.get_session_graph(project_id=PROJECT, session_id=second.session_id)
    assert _measured(_node(won, late.action_id)).execution_id == "agent-exec-1"
    assert _measured(_node(won, late.action_id)).task_id == "task-1"
    lost = groups.get_session_graph(project_id=PROJECT, session_id=first.session_id)
    node = _node(lost, early.action_id)
    assert node.kind == "measurement" and node.status == "link_claimed"
    assert "execution_link_claimed" in node.missing
    measured = _measured(node)
    assert (measured.execution_id, measured.task_id, measured.sequence) == (None, None, None)
    # Its own record still says it was dispatched.
    assert measured.dispatch_status == "queued"
    assert lost.session.counts.measurements == 0

    # The audit must attribute scientific results to the same winning action.
    from qdash.api.services.agent_session_audit import _measurement_facts, _Records

    for session_id, action_id, owns_result in (
        (second.session_id, late.action_id, True),
        (first.session_id, early.action_id, False),
    ):
        session_doc = AgentSessionDocument.find_one({"session_id": session_id}).run()
        assert session_doc is not None
        records = _Records(session_doc)
        action_doc = next(a for a in records.actions if a.action_id == action_id)
        facts, missing = _measurement_facts(records, action_doc)
        assert (action_id in records.task_results) is owns_result
        if not owns_result:
            assert facts["execution_id"] is None
            assert "execution_link_claimed" in missing
            assert "output_parameters" not in facts
            assert records.evaluations == []


def test_duplicate_references_in_one_session_hold_one_execution(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    first = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, first.action_id, sequence=1, start=BASE)
    again = _submit(sessions, session.session_id, key="a-2")
    _set_action(again.action_id, operation_id="flow-1", execution_status="queued")
    third = _submit(sessions, session.session_id, key="a-3")
    _dispatch(session.session_id, third.action_id, sequence=2, start=BASE + timedelta(minutes=1))

    group = groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0]
    assert [(c.action_id, c.sequence) for c in group.children] == [
        (first.action_id, 1),
        (third.action_id, 2),
    ]
    graph = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    assert _measured(_node(graph, third.action_id)).sequence == 2
    duplicate = _node(graph, again.action_id)
    assert duplicate.status == "link_claimed" and _measured(duplicate).task_id is None
    edges = {(e.kind, e.source, e.target) for e in graph.edges}
    assert ("sequence", f"action:{first.action_id}", f"action:{third.action_id}") in edges
    assert not any(again.action_id in source for kind, source, _ in edges if kind == "sequence")


def test_shared_flow_run_id_resolves_to_the_earliest_execution_everywhere(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    _set_action(action.action_id, operation_id="flow-dup", execution_status="queued")
    # The later execution is inserted first.
    _execution("dup-late", start=BASE + timedelta(minutes=5), flow_run_id="flow-dup")
    _execution("dup-early", start=BASE, flow_run_id="flow-dup")
    TaskResultHistoryDocument(
        project_id=PROJECT,
        username=OWNER,
        task_id="task-late",
        name="CheckQubitFrequency",
        upstream_id="",
        status="completed",
        message="",
        input_parameters={},
        output_parameters={},
        output_parameter_names=[],
        run_parameters={},
        note={},
        figure_path=[],
        json_figure_path=[],
        raw_data_path=[],
        start_at=BASE + timedelta(minutes=5),
        end_at=BASE + timedelta(minutes=6),
        elapsed_time=5.0,
        task_type="qubit",
        system_info=SystemInfoModel(),
        qid="Q00",
        execution_id="dup-late",
        tags=[],
        chip_id=CHIP,
    ).insert()

    group = _group(groups.list_groups(project_id=PROJECT, chip_id=CHIP), session.session_id)
    assert [c.execution.execution_id for c in group.children] == ["dup-early"]
    early = link_for_execution(PROJECT, _execution_doc("dup-early"))
    assert early is not None and early.linked
    late = link_for_execution(PROJECT, _execution_doc("dup-late"))
    assert late is None or not late.linked
    node = _node(
        groups.get_session_graph(project_id=PROJECT, session_id=session.session_id),
        action.action_id,
    )
    # The other execution's result is never attributed to the action.
    assert _measured(node).execution_id == "dup-early" and _measured(node).task_id is None
    assert "task_result" in node.missing
    # The session audit resolves the shared flow run id the same way.
    stored = AgentSessionDocument.find_one({"session_id": session.session_id}).run()
    assert stored is not None
    events = AgentSessionAuditService().timeline(stored)
    measured = [e for e in events if e.kind == "measurement"]
    assert [e.execution_id for e in measured] == ["dup-early"]


def test_operation_and_execution_ids_that_disagree_link_nothing(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, action.action_id, sequence=1, start=BASE)
    _execution("manual-x", start=BASE + timedelta(minutes=1))
    _set_action(action.action_id, execution_id="manual-x")

    result = groups.list_groups(project_id=PROJECT, chip_id=CHIP)
    assert result.grouped_executions == 0
    assert {"agent-exec-1", "manual-x"} <= set(_rows(result))
    summary = _summary(_group(result, session.session_id))
    assert any("name different executions" in text for text in summary.missing)
    for execution_id in ("agent-exec-1", "manual-x"):
        link = link_for_execution(PROJECT, _execution_doc(execution_id))
        assert link is None or not link.linked
    node = _node(
        groups.get_session_graph(project_id=PROJECT, session_id=session.session_id),
        action.action_id,
    )
    assert node.status == "link_ambiguous" and "execution_link_ambiguous" in node.missing
    assert _measured(node).execution_id is None and _measured(node).task_id is None


def test_execution_in_another_project_is_missing_not_linked(
    sessions: AgentSessionService, groups: ExecutionGroupService
) -> None:
    session = _session(sessions)
    action = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, action.action_id, sequence=1, start=BASE, project_id=OTHER)
    assert groups.list_groups(project_id=PROJECT, chip_id=CHIP).grouped_executions == 0
    node = _node(
        groups.get_session_graph(project_id=PROJECT, session_id=session.session_id),
        action.action_id,
    )
    assert node.missing == ["execution"] and _measured(node).execution_id is None


# ---------------------------------------------------------------------- read-only graph


def _snapshot() -> dict[str, list[dict[str, Any]]]:
    from qdash.dbmodel.agent_session import AgentInterventionDocument

    return {
        model.__name__: list(model.get_motor_collection().find({}).sort("_id", 1))
        for model in (
            AgentSessionDocument,
            AgentActionDocument,
            AgentInterventionDocument,
            ExecutionHistoryDocument,
        )
    }


@pytest.mark.parametrize("stored", ["active", "waiting_for_human"])
def test_graph_of_overdue_session_with_pending_records_writes_nothing(
    sessions: AgentSessionService, groups: ExecutionGroupService, stored: str
) -> None:
    from qdash.dbmodel.agent_session import AgentInterventionDocument

    session = _session(sessions)
    first = _submit(sessions, session.session_id, key="a-1")
    _dispatch(session.session_id, first.action_id, sequence=1, start=BASE)
    pending = _submit(sessions, session.session_id, key="a-2")
    payload = AgentActionDocument.get_motor_collection().find_one(
        {"action_id": pending.action_id}, {"_id": 0}
    )
    AgentActionDocument.get_motor_collection().delete_one({"action_id": pending.action_id})
    opened = sessions.interventions.create_intervention(
        project_id=PROJECT,
        session_id=session.session_id,
        username=OWNER,
        body=CreateAgentInterventionRequest.model_validate(
            {
                "idempotency_key": "human-1",
                "reason": "evaluation_failed",
                "summary": "R2 is low.",
                "question": "Widen the sweep or stop?",
                "qids": ["Q00"],
                "autonomous": True,
            }
        ),
    )
    # As a crash between the counting update and the record writes leaves them.
    intervention = AgentInterventionDocument.get_motor_collection().find_one(
        {"intervention_id": opened.intervention_id}, {"_id": 0}
    )
    AgentInterventionDocument.get_motor_collection().delete_one(
        {"intervention_id": opened.intervention_id}
    )
    AgentSessionDocument.get_motor_collection().update_one(
        {"session_id": session.session_id},
        {
            "$set": {
                "status": stored,
                "pending_action": payload,
                "pending_intervention": {"intervention": intervention},
                "expires_at": datetime.now(UTC) - timedelta(minutes=1),
            }
        },
    )

    before = _snapshot()
    graph = groups.get_session_graph(project_id=PROJECT, session_id=session.session_id)
    assert _snapshot() == before

    assert graph.session.status == AgentSessionStatus.EXPIRED
    assert graph.session.stored_status == AgentSessionStatus(stored)
    assert f"action record {pending.action_id} (pending write)" in graph.session.missing
    assert f"intervention record {opened.intervention_id} (pending write)" in graph.session.missing
    node = _node(graph, pending.action_id)
    assert "action_record" in node.missing
    asked = next(n for n in graph.nodes if n.kind == "intervention")
    assert _asked(asked).intervention_id == opened.intervention_id

    listed = _summary(groups.list_groups(project_id=PROJECT, chip_id=CHIP).items[0])
    assert listed.status == AgentSessionStatus.EXPIRED
    assert f"action record {pending.action_id} (pending write)" in listed.missing
    assert _snapshot() == before
