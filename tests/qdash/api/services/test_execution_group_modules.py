"""Tests for the seams between the grouped Execution list, the session graph, and their facade.

The router-facing service keeps its import path and names, and the helpers the list and the
graph share number measurements and merge unwritten actions as both views expect.
Behavior of the views themselves is covered in ``test_execution_group_service.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from qdash.api.services import (
    agent_session_graph,
    agent_session_group_summary,
    execution_group_rows,
    execution_group_service,
)
from qdash.api.services.agent_execution_links import UnlinkedAction
from qdash.datamodel.agent_session import AgentActionDecision, AgentActionType
from qdash.dbmodel.agent_session import AgentActionDocument, AgentSessionDocument

BASE = datetime(2026, 11, 20, tzinfo=UTC)


def _action(
    action_id: str,
    version: int,
    *,
    task: str = "CheckRabi",
    qids: tuple[str, ...] = ("0",),
    decision: AgentActionDecision = AgentActionDecision.AUTHORIZED,
    action_type: AgentActionType = AgentActionType.RUN_TASK,
    execution_id: str | None = "exec",
) -> AgentActionDocument:
    return AgentActionDocument.model_construct(  # type: ignore[no-any-return]
        action_id=action_id,
        session_id="session-1",
        state_version_before=version,
        created_at=BASE + timedelta(minutes=version),
        action_type=action_type,
        decision=decision,
        task_name=task,
        qids=list(qids),
        operation_id=None,
        execution_id=execution_id,
    )


def test_facade_keeps_router_names_and_limits() -> None:
    service = execution_group_service
    assert service.MAX_LIST_CHILDREN is execution_group_rows.MAX_LIST_CHILDREN
    assert service.MAX_LIST_RUNS is execution_group_rows.MAX_LIST_RUNS
    assert service.MAX_LIST_AGENT_SESSIONS is execution_group_rows.MAX_LIST_AGENT_SESSIONS
    assert service.MAX_SESSION_GRAPH_NODES is agent_session_graph.MAX_SESSION_GRAPH_NODES
    assert service.SESSION_GRAPH_NOTES is agent_session_graph.SESSION_GRAPH_NOTES
    assert service.run_target_qids is execution_group_rows.run_target_qids
    assert callable(service.ExecutionGroupService(None).list_groups)  # type: ignore[arg-type]


def test_measurement_numbers_order_attempts_and_skip_conflicts() -> None:
    first = _action("a1", 1)
    rejected = _action("a2", 2, decision=AgentActionDecision.REJECTED)
    retry = _action("a3", 3)
    other = _action("a4", 4, qids=("1",))
    undispatched = _action("a5", 5, execution_id=None)
    conflicted = _action("a6", 6)
    unlinked = {
        "a6": UnlinkedAction(
            session_id="session-1",
            action_id="a6",
            reason="ambiguous",
            execution_ids=("x", "y"),
        )
    }
    # Input order does not matter: state versions order a session's actions.
    numbers = agent_session_group_summary.measurement_numbers(
        [conflicted, other, undispatched, retry, rejected, first], unlinked
    )
    assert numbers == {"a1": (1, 1), "a3": (2, 2), "a4": (3, 1)}


def test_with_pending_adds_unwritten_actions_once(init_db: Any) -> None:
    stored = _action("a1", 1)
    pending: dict[str, Any] = {
        "action_id": "a2",
        "session_id": "session-1",
        "project_id": "project-1",
        "action_type": AgentActionType.RUN_TASK.value,
        "decision": AgentActionDecision.AUTHORIZED.value,
        "idempotency_key": "key-2",
        "request_hash": "hash-2",
        "reason": "Measure the Rabi rate.",
        "state_version_before": 2,
        "state_version_after": 3,
        "task_name": "CheckRabi",
        "qids": ["0"],
    }
    session = AgentSessionDocument.model_construct(
        pending_action=pending,
        pending_intervention={"action": {"action_id": "a1"}},
    )
    merged = agent_session_group_summary.with_pending(session, [stored])
    assert [a.action_id for a in merged] == ["a1", "a2"]
