"""Resume eligibility policy for paused agent sessions.

This module decides, from facts already loaded, why an intervention cannot resume its
session. It reads nothing from the database: ``AgentInterventionService`` loads the
session, the intervention, and QDash's record of the plan's actions, asks this policy for
blockers, then adds the in-flight operation blockers and applies the atomic update.

Blockers are sentences an expert can act on, returned in a fixed order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from qdash.datamodel.agent_session import AgentInterventionStatus, AgentSessionStatus

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from qdash.datamodel.agent_session import AgentPlanCheckpoint


@dataclass(frozen=True)
class PlanResumeFacts:
    """What is known of an intervention's plan checkpoint when deciding a resume.

    Attributes
    ----------
    checkpoint
        The plan checkpoint the intervention recorded.
    approved
        Whether the session's plan binding identifies this checkpoint's plan.
    history_errors
        Actions QDash recorded that do not fit the plan, as blocker sentences.
    node_visits
        Visits per plan node, the larger of the runner's and QDash's counts.
    node_executions
        Node executions so far, the larger of the runner's and QDash's counts.
    """

    checkpoint: AgentPlanCheckpoint
    approved: bool
    history_errors: Sequence[str]
    node_visits: Mapping[str, int]
    node_executions: int


def node_budget_blocker(
    checkpoint: AgentPlanCheckpoint, node_visits: Mapping[str, int], node_id: str
) -> str | None:
    """Why one plan node cannot run again under the plan's visit limit, if it cannot."""
    visits = node_visits.get(node_id, 0)
    if checkpoint.max_node_visits is not None and visits >= checkpoint.max_node_visits:
        return (
            f"Node {node_id} already ran {visits} times, the plan's limit; "
            "choose another node or start a newly authorized session"
        )
    return None


def resume_blockers(
    *,
    intervention_id: str,
    intervention_status: AgentInterventionStatus,
    expected_status: AgentInterventionStatus,
    session_status: AgentSessionStatus,
    active_intervention_id: str | None,
    action_count: int,
    max_actions: int,
    plan: PlanResumeFacts | None,
    resume_node_id: str | None,
) -> list[str]:
    """Why a resume cannot happen, excluding operations still in flight.

    The checks run in order: intervention status, session status, the session's action
    budget, then (for a plan) plan approval, recorded history, node execution budget,
    and the resume node. ``resume_node_id`` defaults to the checkpoint's stopped node.
    """
    blockers: list[str] = []
    if intervention_status != expected_status:
        blockers.append(f"The intervention is {intervention_status.value.replace('_', ' ')}")
    if session_status == AgentSessionStatus.EXPIRED:
        blockers.append("The session expired; a newly authorized session is needed to continue")
    elif session_status in {AgentSessionStatus.COMPLETED, AgentSessionStatus.CANCELLED}:
        blockers.append(
            f"The session is {session_status.value}; it is not reactivated, so a newly "
            "authorized session is needed to continue"
        )
    elif (
        session_status != AgentSessionStatus.WAITING_FOR_HUMAN
        or active_intervention_id != intervention_id
    ):
        blockers.append("The session is not paused on this intervention")
    remaining_actions = max_actions - action_count
    if remaining_actions <= 0:
        blockers.append(
            f"The session used all {max_actions} of its actions; "
            "a newly authorized session is needed to measure again"
        )
    if plan is not None:
        checkpoint = plan.checkpoint
        if not plan.approved:
            blockers.append(
                "The checkpoint is not the plan this session approved; a newly "
                "authorized session is needed to run it"
            )
        blockers.extend(plan.history_errors)
        remaining_nodes = checkpoint.max_node_executions - plan.node_executions
        if remaining_nodes <= 0:
            blockers.append(
                f"The plan used all {checkpoint.max_node_executions} of its node "
                "executions; a newly authorized plan is needed"
            )
        elif 0 < remaining_actions < remaining_nodes:
            blockers.append(
                f"The plan may still run {remaining_nodes} nodes but the session has "
                f"{remaining_actions} actions left"
            )
        node_id = resume_node_id or checkpoint.stopped_node_id
        if node_id not in {node.id for node in checkpoint.nodes}:
            blockers.append(f"Node {node_id} is not part of the approved plan")
        else:
            node_blocker = node_budget_blocker(checkpoint, plan.node_visits, node_id)
            if node_blocker:
                blockers.append(node_blocker)
    return blockers
