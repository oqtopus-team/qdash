"""Tests for the pure resume eligibility policy of agent interventions."""

from __future__ import annotations

from typing import Any

from qdash.api.services.agent_resume_policy import (
    PlanResumeFacts,
    node_budget_blocker,
    resume_blockers,
)
from qdash.datamodel.agent_session import (
    AgentInterventionStatus,
    AgentPlanCheckpoint,
    AgentSessionStatus,
)

OPEN = AgentInterventionStatus.OPEN
WAITING = AgentSessionStatus.WAITING_FOR_HUMAN


def _checkpoint(**overrides: Any) -> AgentPlanCheckpoint:
    data: dict[str, Any] = {
        "qid": "Q00",
        "nodes": [
            {"id": "rabi", "task_name": "CheckRabi", "candidate_parameter": "control_amplitude"},
            {
                "id": "chevron",
                "task_name": "CheckChevron",
                "candidate_parameter": "qubit_frequency",
            },
        ],
        "idempotency_prefix": "plan-1",
        "stopped_node_id": "rabi",
        "max_node_executions": 4,
        "max_node_visits": 2,
    }
    data.update(overrides)
    return AgentPlanCheckpoint.model_validate(data)


def _plan(
    checkpoint: AgentPlanCheckpoint | None = None,
    *,
    approved: bool = True,
    history_errors: tuple[str, ...] = (),
    node_visits: dict[str, int] | None = None,
    node_executions: int = 0,
) -> PlanResumeFacts:
    return PlanResumeFacts(
        checkpoint=checkpoint or _checkpoint(),
        approved=approved,
        history_errors=history_errors,
        node_visits=node_visits or {},
        node_executions=node_executions,
    )


def _blockers(**overrides: Any) -> list[str]:
    facts: dict[str, Any] = {
        "intervention_id": "int-1",
        "intervention_status": OPEN,
        "expected_status": OPEN,
        "session_status": WAITING,
        "active_intervention_id": "int-1",
        "action_count": 0,
        "max_actions": 10,
        "plan": None,
        "resume_node_id": None,
    }
    facts.update(overrides)
    return resume_blockers(**facts)


def test_an_eligible_resume_has_no_blockers() -> None:
    assert _blockers() == []
    assert _blockers(plan=_plan()) == []


def test_intervention_and_session_status_blockers() -> None:
    assert _blockers(intervention_status=AgentInterventionStatus.RESUME_AUTHORIZED) == [
        "The intervention is resume authorized"
    ]
    assert _blockers(session_status=AgentSessionStatus.EXPIRED, active_intervention_id=None) == [
        "The session expired; a newly authorized session is needed to continue"
    ]
    assert _blockers(session_status=AgentSessionStatus.CANCELLED) == [
        "The session is cancelled; it is not reactivated, so a newly "
        "authorized session is needed to continue"
    ]
    assert _blockers(session_status=AgentSessionStatus.COMPLETED) == [
        "The session is completed; it is not reactivated, so a newly "
        "authorized session is needed to continue"
    ]
    assert _blockers(session_status=AgentSessionStatus.ACTIVE) == [
        "The session is not paused on this intervention"
    ]
    assert _blockers(active_intervention_id="int-2") == [
        "The session is not paused on this intervention"
    ]


def test_every_blocker_is_reported_in_order() -> None:
    plan = _plan(
        approved=False,
        history_errors=("Action a-1 ran outside plan plan-1",),
        node_executions=4,
    )
    assert _blockers(
        intervention_status=AgentInterventionStatus.STOPPED,
        session_status=AgentSessionStatus.CANCELLED,
        action_count=10,
        plan=plan,
        resume_node_id="unknown",
    ) == [
        "The intervention is stopped",
        "The session is cancelled; it is not reactivated, so a newly "
        "authorized session is needed to continue",
        "The session used all 10 of its actions; "
        "a newly authorized session is needed to measure again",
        "The checkpoint is not the plan this session approved; a newly "
        "authorized session is needed to run it",
        "Action a-1 ran outside plan plan-1",
        "The plan used all 4 of its node executions; a newly authorized plan is needed",
        "Node unknown is not part of the approved plan",
    ]


def test_remaining_nodes_beyond_remaining_actions_blocks_resume() -> None:
    assert _blockers(action_count=8, plan=_plan(node_executions=1)) == [
        "The plan may still run 3 nodes but the session has 2 actions left"
    ]
    # With no actions left only the action budget is reported.
    assert _blockers(action_count=10, plan=_plan(node_executions=1)) == [
        "The session used all 10 of its actions; "
        "a newly authorized session is needed to measure again"
    ]


def test_resume_node_defaults_to_the_stopped_node_and_checks_its_visits() -> None:
    plan = _plan(node_visits={"rabi": 2})
    expected = (
        "Node rabi already ran 2 times, the plan's limit; "
        "choose another node or start a newly authorized session"
    )
    assert _blockers(plan=plan) == [expected]
    assert _blockers(plan=plan, resume_node_id="chevron") == []


def test_node_budget_blocker_without_a_visit_limit() -> None:
    checkpoint = _checkpoint(max_node_visits=None)
    assert node_budget_blocker(checkpoint, {"rabi": 99}, "rabi") is None
    assert node_budget_blocker(_checkpoint(), {"rabi": 1}, "rabi") is None
    assert node_budget_blocker(_checkpoint(), {}, "chevron") is None
