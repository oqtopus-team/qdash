"""HTTP endpoints for policy-governed local agent sessions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from qdash.api.dependencies import get_agent_session_service, get_flow_service
from qdash.api.lib.project import (
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.agent_session import (
    AgentActionResponse,
    AgentCampaignCommitResponse,
    AgentCandidateCommitResponse,
    AgentSessionResponse,
    ApplyAgentCandidateRequest,
    CandidateGateResponse,
    CommitAgentCampaignRequest,
    CommitAgentCandidateRequest,
    CreateAgentSessionRequest,
    EvaluateCandidateGateRequest,
    ExecuteAgentActionRequest,
    ListAgentActionsResponse,
    ListAgentCandidatesResponse,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_session_service import AgentSessionService
from qdash.api.services.flow_service import FlowService

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
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentActionResponse:
    """Authorize and audit an action proposal without executing it."""
    return service.submit_action(
        project_id=ctx.project_id,
        session_id=session_id,
        body=body,
    )


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
    "/{session_id}/campaign-commits",
    response_model=AgentCampaignCommitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Commit final agent campaign candidates",
    operation_id="commitAgentCampaignCandidates",
)
def commit_agent_campaign_candidates(
    session_id: str,
    body: CommitAgentCampaignRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentCampaignCommitResponse:
    """Validate a final candidate set and persist it with one Qubit save."""
    return service.commit_campaign_candidates(
        project_id=ctx.project_id,
        session_id=session_id,
        username=ctx.user.username,
        body=body,
    )


@router.get(
    "/{session_id}/campaign-commits/{commit_id}",
    response_model=AgentCampaignCommitResponse,
    summary="Get an agent campaign commit",
    operation_id="getAgentCampaignCommit",
)
def get_agent_campaign_commit(
    session_id: str,
    commit_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[AgentSessionService, Depends(get_agent_session_service)],
) -> AgentCampaignCommitResponse:
    """Get one audited final campaign candidate-set commit."""
    return service.get_campaign_commit(
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
) -> AgentActionResponse:
    """Dispatch one authorized run-task action to the system workflow."""
    return await service.execute_action(
        project_id=ctx.project_id,
        session_id=session_id,
        action_id=action_id,
        body=body,
        flow_service=flow_service,
    )
