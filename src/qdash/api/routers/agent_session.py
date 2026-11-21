"""HTTP endpoints for policy-governed local agent sessions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status

from qdash.api.dependencies import (
    get_agent_intervention_service,
    get_agent_session_service,
    get_flow_service,
    get_task_file_service,
)
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.agent_session import (
    AgentActionResponse,
    AgentCandidateCommitResponse,
    AgentCandidateSetCommitResponse,
    AgentInterventionResponse,
    AgentSessionResponse,
    ApplyAgentCandidateRequest,
    CandidateGateResponse,
    ClaimAgentResumeRequest,
    CommitAgentCandidateRequest,
    CommitAgentCandidateSetRequest,
    CreateAgentInterventionRequest,
    CreateAgentSessionRequest,
    EvaluateCandidateGateRequest,
    ExecuteAgentActionRequest,
    ListAgentActionsResponse,
    ListAgentCandidatesResponse,
    ListAgentInterventionsResponse,
    RecordAgentResumeOutcomeRequest,
    RespondAgentInterventionRequest,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.api.services.flow_service import FlowService
from qdash.api.services.task_file_service import TaskFileService

router = APIRouter(prefix="/agent-sessions")


@router.post(
    "",
    response_model=AgentSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an agent session",
    operation_id="createAgentSession",
)
def create_agent_session(
    body: CreateAgentSessionRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentSessionResponse:
    """Create a bounded authorization scope for a user-operated local agent."""
    return service.create_session(
        project_id=ctx.project_id,
        username=ctx.user.username,
        body=body,
    )


@router.get(
    "/{session_id}",
    response_model=AgentSessionResponse,
    summary="Get an agent session",
    operation_id="getAgentSession",
)
def get_agent_session(
    session_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentSessionResponse:
    """Get authoritative state for an agent session."""
    return service.get_session(project_id=ctx.project_id, session_id=session_id)


@router.post(
    "/{session_id}/candidate-gate",
    response_model=CandidateGateResponse,
    summary="Evaluate an agent candidate",
    operation_id="evaluateAgentCandidateGate",
)
def evaluate_agent_candidate_gate(
    session_id: str,
    body: EvaluateCandidateGateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> CandidateGateResponse:
    """Evaluate a numeric candidate against session-owned bounds without writing it."""
    return service.evaluate_candidate_gate(
        project_id=ctx.project_id,
        session_id=session_id,
        body=body,
    )


@router.post(
    "/{session_id}/actions",
    response_model=AgentActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an agent action",
    operation_id="submitAgentAction",
)
def submit_agent_action(
    session_id: str,
    body: SubmitAgentActionRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentActionResponse:
    """Authorize and audit an action proposal without executing it.

    An authorized ``request_human`` also records an intervention, pauses the session on it,
    and queues its Slack message.
    """
    action = service.submit_action(
        project_id=ctx.project_id,
        session_id=session_id,
        body=body,
        username=ctx.user.username,
    )
    if action.intervention_id:
        background_tasks.add_task(
            service.interventions.deliver_notification, action.intervention_id
        )
    return action


@router.get(
    "/{session_id}/actions",
    response_model=ListAgentActionsResponse,
    summary="List agent actions",
    operation_id="listAgentActions",
)
def list_agent_actions(
    session_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> ListAgentActionsResponse:
    """List the ordered audit trail for an agent session."""
    return service.list_actions(project_id=ctx.project_id, session_id=session_id)


@router.get(
    "/{session_id}/actions/{action_id}/candidates",
    response_model=ListAgentCandidatesResponse,
    summary="List agent action candidates",
    operation_id="listAgentActionCandidates",
)
def list_agent_action_candidates(
    session_id: str,
    action_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> ListAgentCandidatesResponse:
    """Read candidates and provenance from an action's authoritative task result."""
    return service.list_action_candidates(
        project_id=ctx.project_id,
        session_id=session_id,
        action_id=action_id,
    )


@router.post(
    "/{session_id}/actions/{action_id}/candidates/{parameter_name}/commit",
    response_model=AgentCandidateCommitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Commit an agent action candidate",
    operation_id="commitAgentActionCandidate",
)
def commit_agent_action_candidate(
    session_id: str,
    action_id: str,
    parameter_name: str,
    body: CommitAgentCandidateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentCandidateCommitResponse:
    """Commit a revalidated task-result candidate into QDash calibration state."""
    return service.commit_action_candidate(
        project_id=ctx.project_id,
        session_id=session_id,
        action_id=action_id,
        parameter_name=parameter_name,
        username=ctx.user.username,
        body=body,
    )


@router.post(
    "/{session_id}/candidate-set-commits",
    response_model=AgentCandidateSetCommitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Commit the final agent candidate set",
    operation_id="commitAgentCandidateSet",
)
def commit_agent_candidate_set(
    session_id: str,
    body: CommitAgentCandidateSetRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentCandidateSetCommitResponse:
    """Validate a final candidate set and persist it with one Qubit save."""
    return service.commit_candidate_set(
        project_id=ctx.project_id,
        session_id=session_id,
        username=ctx.user.username,
        body=body,
    )


@router.get(
    "/{session_id}/candidate-set-commits/{commit_id}",
    response_model=AgentCandidateSetCommitResponse,
    summary="Get an agent candidate set commit",
    operation_id="getAgentCandidateSetCommit",
)
def get_agent_candidate_set_commit(
    session_id: str,
    commit_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentCandidateSetCommitResponse:
    """Get one audited final candidate-set commit."""
    return service.get_candidate_set_commit(
        project_id=ctx.project_id,
        session_id=session_id,
        commit_id=commit_id,
    )


@router.get(
    "/{session_id}/commits/{commit_id}",
    response_model=AgentCandidateCommitResponse,
    summary="Get an agent candidate commit",
    operation_id="getAgentCandidateCommit",
)
def get_agent_candidate_commit(
    session_id: str,
    commit_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentCandidateCommitResponse:
    """Get commit persistence and worker-side backend apply state."""
    return service.get_candidate_commit(
        project_id=ctx.project_id,
        session_id=session_id,
        commit_id=commit_id,
    )


@router.post(
    "/{session_id}/commits/{commit_id}/apply",
    response_model=AgentCandidateCommitResponse,
    summary="Apply an agent candidate commit to the backend",
    operation_id="applyAgentCandidateCommit",
)
async def apply_agent_candidate_commit(
    session_id: str,
    commit_id: str,
    body: ApplyAgentCandidateRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
    flow_service: Annotated[FlowService, Depends(get_flow_service)],
) -> AgentCandidateCommitResponse:
    """Dispatch a committed, gated candidate to the worker-side backend."""
    return await service.apply_candidate_to_backend(
        project_id=ctx.project_id,
        session_id=session_id,
        commit_id=commit_id,
        body=body,
        flow_service=flow_service,
    )


@router.get(
    "/{session_id}/actions/{action_id}",
    response_model=AgentActionResponse,
    summary="Get an agent action",
    operation_id="getAgentAction",
)
def get_agent_action(
    session_id: str,
    action_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentActionResponse:
    """Get one action and its current dispatch status."""
    return service.get_action(
        project_id=ctx.project_id,
        session_id=session_id,
        action_id=action_id,
    )


@router.post(
    "/{session_id}/actions/{action_id}/execute",
    response_model=AgentActionResponse,
    summary="Execute an authorized agent action",
    operation_id="executeAgentAction",
)
async def execute_agent_action(
    session_id: str,
    action_id: str,
    body: ExecuteAgentActionRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
    flow_service: Annotated[FlowService, Depends(get_flow_service)],
    task_file_service: Annotated[TaskFileService, Depends(get_task_file_service)],
) -> AgentActionResponse:
    """Dispatch one authorized run-task action to the system workflow."""
    return await service.execute_action(
        project_id=ctx.project_id,
        session_id=session_id,
        action_id=action_id,
        body=body,
        flow_service=flow_service,
        task_file_service=task_file_service,
    )


InterventionService = Annotated[AgentInterventionService, Depends(get_agent_intervention_service)]


@router.post(
    "/{session_id}/interventions",
    response_model=AgentInterventionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record an agent intervention",
    operation_id="createAgentIntervention",
)
def create_agent_intervention(
    session_id: str,
    body: CreateAgentInterventionRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: InterventionService,
) -> AgentInterventionResponse:
    """Record that the agent needs a person and pause the session if it is active.

    The record is saved before any Slack message is attempted, and it is saved even when the
    session has no actions left or has expired.
    """
    intervention = service.create_intervention(
        project_id=ctx.project_id,
        session_id=session_id,
        username=ctx.user.username,
        body=body,
    )
    background_tasks.add_task(service.deliver_notification, intervention.intervention_id)
    return intervention


@router.get(
    "/{session_id}/interventions",
    response_model=ListAgentInterventionsResponse,
    summary="List agent interventions",
    operation_id="listAgentInterventions",
)
def list_agent_interventions(
    session_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: InterventionService,
) -> ListAgentInterventionsResponse:
    """List a session's interventions, newest first."""
    return service.list_interventions(project_id=ctx.project_id, session_id=session_id)


@router.get(
    "/{session_id}/interventions/{intervention_id}",
    response_model=AgentInterventionResponse,
    summary="Get an agent intervention",
    operation_id="getAgentIntervention",
)
def get_agent_intervention(
    session_id: str,
    intervention_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: InterventionService,
) -> AgentInterventionResponse:
    """Get an intervention with the session state needed to answer it."""
    return service.get_intervention(
        project_id=ctx.project_id, session_id=session_id, intervention_id=intervention_id
    )


@router.post(
    "/{session_id}/interventions/{intervention_id}/respond",
    response_model=AgentInterventionResponse,
    summary="Respond to an agent intervention",
    operation_id="respondAgentIntervention",
)
def respond_agent_intervention(
    session_id: str,
    intervention_id: str,
    body: RespondAgentInterventionRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: InterventionService,
) -> AgentInterventionResponse:
    """Record an expert's guidance and either stop the session or authorize a resume.

    A plan with a checkpoint stays paused until its runner claims the resume.
    """
    result = service.respond(
        project_id=ctx.project_id,
        session_id=session_id,
        intervention_id=intervention_id,
        username=ctx.user.username,
        body=body,
    )
    text = {
        "stopped": f"{ctx.user.username} stopped the session.",
        "resumed": f"{ctx.user.username} reactivated the session for the agent.",
        "resume_authorized": (
            f"{ctx.user.username} authorized a resume; the plan continues when its runner "
            "claims it."
        ),
    }.get(result.status.value)
    if text:
        background_tasks.add_task(service.post_update, intervention_id, text)
    return result


@router.post(
    "/{session_id}/interventions/{intervention_id}/claim-resume",
    response_model=AgentInterventionResponse,
    summary="Claim an authorized agent resume",
    operation_id="claimAgentInterventionResume",
)
def claim_agent_intervention_resume(
    session_id: str,
    intervention_id: str,
    body: ClaimAgentResumeRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: InterventionService,
) -> AgentInterventionResponse:
    """Reactivate the paused session for the one runner that holds the claim key."""
    result = service.claim_resume(
        project_id=ctx.project_id,
        session_id=session_id,
        intervention_id=intervention_id,
        username=ctx.user.username,
        body=body,
    )
    background_tasks.add_task(
        service.post_update, intervention_id, f"The runner of {ctx.user.username} resumed the plan."
    )
    return result


@router.post(
    "/{session_id}/interventions/{intervention_id}/resume-outcome",
    response_model=AgentInterventionResponse,
    summary="Record the outcome of a resumed agent plan",
    operation_id="recordAgentResumeOutcome",
)
def record_agent_resume_outcome(
    session_id: str,
    intervention_id: str,
    body: RecordAgentResumeOutcomeRequest,
    background_tasks: BackgroundTasks,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: InterventionService,
) -> AgentInterventionResponse:
    """Record how the resumed run ended."""
    result = service.record_resume_outcome(
        project_id=ctx.project_id,
        session_id=session_id,
        intervention_id=intervention_id,
        username=ctx.user.username,
        body=body,
    )
    background_tasks.add_task(
        service.post_update, intervention_id, f"The resumed plan ended: {body.transition}."
    )
    return result


@router.post(
    "/{session_id}/interventions/{intervention_id}/notification/retry",
    response_model=AgentInterventionResponse,
    summary="Retry an agent intervention Slack message",
    operation_id="retryAgentInterventionNotification",
)
def retry_agent_intervention_notification(
    session_id: str,
    intervention_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: InterventionService,
) -> AgentInterventionResponse:
    """Try once more to send an unsent Slack message; a sent message is never posted again."""
    return service.retry_notification(
        project_id=ctx.project_id,
        session_id=session_id,
        intervention_id=intervention_id,
        username=ctx.user.username,
    )
