"""API schemas for policy-governed local agent sessions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic resolves this runtime annotation
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentInterventionAttempt,
    AgentInterventionDecision,
    AgentInterventionEvent,
    AgentInterventionReason,
    AgentInterventionResponseRecord,
    AgentInterventionStatus,
    AgentNotificationStatus,
    AgentPlanCheckpoint,
    AgentResumeOutcomeRecord,
    AgentSessionPolicy,
    AgentSessionStatus,
)


class CreateAgentSessionRequest(BaseModel):
    """Create a bounded authorization session for a local agent."""

    chip_id: str = Field(min_length=1, max_length=200)
    policy: AgentSessionPolicy
    expires_in_seconds: int = Field(default=21_600, ge=60, le=86_400)
    skill_name: str = Field(default="", max_length=200)
    skill_version: str = Field(default="", max_length=200)
    skill_hash: str = Field(default="", max_length=256)
    model_name: str = Field(default="", max_length=300)


class AgentSessionResponse(BaseModel):
    """Authoritative state returned for an agent session."""

    session_id: str
    project_id: str
    chip_id: str
    created_by: str
    policy: AgentSessionPolicy
    skill_name: str
    skill_version: str
    skill_hash: str
    model_name: str
    status: AgentSessionStatus
    state_version: int
    action_count: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    active_intervention_id: str | None = Field(
        default=None, description="The intervention the session waits on, if any"
    )


class SubmitAgentActionRequest(BaseModel):
    """Submit an action proposal for platform-side authorization."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=0)
    action_type: AgentActionType
    task_name: str | None = Field(default=None, max_length=200)
    qids: list[str] = Field(default_factory=list)
    parameter_overrides: dict[str, Annotated[float, Field(allow_inf_nan=False)]] = Field(
        default_factory=dict
    )
    diagnosis: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def validate_action_shape(self) -> SubmitAgentActionRequest:
        """Require task details only for run-task proposals."""
        if self.action_type == AgentActionType.RUN_TASK:
            if not self.task_name:
                raise ValueError("task_name is required for run_task")
            if not self.qids:
                raise ValueError("qids is required for run_task")
            return self
        if self.task_name is not None or self.qids or self.parameter_overrides:
            raise ValueError("task_name, qids, and parameter_overrides are only valid for run_task")
        return self


class AgentActionResponse(BaseModel):
    """Platform authorization result for an action proposal."""

    action_id: str
    session_id: str
    idempotency_key: str
    action_type: AgentActionType
    task_name: str | None
    qids: list[str]
    parameter_overrides: dict[str, float]
    diagnosis: str
    decision: AgentActionDecision
    reason: str
    execution_status: str
    operation_id: str | None = None
    execution_id: str | None = None
    state_version_before: int
    state_version_after: int
    created_at: datetime
    intervention_id: str | None = Field(
        default=None, description="Intervention recorded for an authorized request_human"
    )


class ListAgentActionsResponse(BaseModel):
    """Ordered audit records for one agent session."""

    items: list[AgentActionResponse]
    total: int


class ExecuteAgentActionRequest(BaseModel):
    """Dispatch one authorized run-task action as a staged measurement."""

    source_execution_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Execution the action was decided from, kept for provenance. The run reads the "
            "current calibration state, as a Task Workbench run does."
        ),
    )
    update_params: bool = False
    reconfigure: bool = False

    @model_validator(mode="after")
    def require_staged_execution(self) -> ExecuteAgentActionRequest:
        """Prevent bypassing the candidate gate through direct parameter write-back."""
        if self.update_params:
            raise ValueError("agent actions must use update_params=false")
        return self


class EvaluateCandidateGateRequest(BaseModel):
    """Evaluate one numeric candidate against session-owned parameter bounds."""

    parameter_name: str = Field(min_length=1, max_length=200)
    value: float = Field(allow_inf_nan=False)


class CandidateGateResponse(BaseModel):
    """Side-effect-free deterministic decision for one candidate value."""

    session_id: str
    parameter_name: str
    value: float
    accepted: bool
    reason: str
    minimum: float | None = None
    maximum: float | None = None


class AgentCandidateResponse(BaseModel):
    """A numeric candidate derived from an authoritative task result."""

    session_id: str
    action_id: str
    execution_id: str
    task_id: str
    task_name: str
    qid: str
    source_parameter_name: str
    parameter_name: str
    value: float
    error: float = 0.0
    unit: str = ""
    value_type: str = "float"
    quality_metrics: dict[str, float] = Field(default_factory=dict)
    accepted: bool
    reason: str
    minimum: float | None = None
    maximum: float | None = None


class ListAgentCandidatesResponse(BaseModel):
    """Task-result candidates and their deterministic gate decisions."""

    items: list[AgentCandidateResponse]
    total: int


class CommitAgentCandidateRequest(BaseModel):
    """Commit one server-derived candidate into authoritative calibration state."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=0)
    task_id: str = Field(min_length=1, max_length=200)


class AgentCandidateReference(BaseModel):
    """Identify one authoritative accepted candidate for plan finalization."""

    action_id: str = Field(min_length=1, max_length=200)
    parameter_name: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=200)


class CommitAgentCandidateSetRequest(BaseModel):
    """Commit the final accepted candidate set for one same-qubit plan."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=0)
    candidates: list[AgentCandidateReference] = Field(min_length=1, max_length=100)


class ApplyAgentCandidateRequest(BaseModel):
    """Dispatch a committed candidate for worker-side backend application."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=0)
    push_to_github: bool = False


class AgentCandidateCommitResponse(BaseModel):
    """Audited result of committing a gated candidate."""

    commit_id: str
    session_id: str
    action_id: str
    idempotency_key: str
    execution_id: str
    task_id: str
    task_name: str
    qid: str
    parameter_name: str
    value: float
    status: str
    reason: str
    before_snapshot: dict[str, object] | None = None
    after_snapshot: dict[str, object] | None = None
    committed_by: str
    state_version_before: int
    state_version_after: int
    created_at: datetime
    committed_at: datetime | None = None
    backend_status: str = "not_started"
    backend_operation_id: str | None = None
    backend_name: str = ""
    backend_target_files: list[str] = Field(default_factory=list)
    backend_changed_files: list[str] = Field(default_factory=list)
    backend_verified: bool = False
    backend_base_git_commit: str | None = None
    backend_git_commit: str | None = None
    backend_error: str = ""
    backend_requested_at: datetime | None = None
    backend_applied_at: datetime | None = None


class AgentCandidateSetCommitResponse(BaseModel):
    """Audited all-at-once QDash commit of the final candidate set."""

    commit_id: str
    session_id: str
    idempotency_key: str
    chip_id: str
    qid: str
    candidates: list[AgentCandidateResponse]
    status: str
    reason: str
    before_snapshot: dict[str, object] = Field(default_factory=dict)
    after_snapshot: dict[str, object] = Field(default_factory=dict)
    committed_by: str
    state_version_before: int
    state_version_after: int
    created_at: datetime
    committed_at: datetime | None = None


class CreateAgentInterventionRequest(BaseModel):
    """Record that an agent stopped and needs a person, with evidence references.

    QDash records the request even when the session has no actions left or has expired; it
    then pauses the session if it was active. Attempts reference actions, executions, task
    results, and evaluations that QDash checks; free text stays short and human-facing.
    """

    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: AgentInterventionReason
    summary: str = Field(min_length=1, max_length=2000)
    question: str = Field(min_length=1, max_length=2000)
    node_id: str | None = Field(default=None, min_length=1, max_length=200)
    task_name: str | None = Field(default=None, min_length=1, max_length=200)
    qids: list[str] = Field(default_factory=list, max_length=64)
    attempts: list[AgentInterventionAttempt] = Field(default_factory=list, max_length=20)
    checkpoint: AgentPlanCheckpoint | None = Field(
        default=None,
        description="Where the plan stopped; required for a runner to resume it",
    )
    previous_intervention_id: str | None = Field(default=None, min_length=1, max_length=200)


class RespondAgentInterventionRequest(BaseModel):
    """An expert's answer: resume within the approved plan, or stop the session.

    Guidance is recorded for the agent and the audit trail; it does not change the plan,
    the scope, or any parameter.
    """

    idempotency_key: str = Field(min_length=1, max_length=128)
    expected_state_version: int = Field(ge=0)
    decision: AgentInterventionDecision
    guidance: str = Field(default="", max_length=5000)
    resume_node_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Plan node to continue from; defaults to the node where the plan stopped",
    )

    @model_validator(mode="after")
    def validate_resume_node(self) -> RespondAgentInterventionRequest:
        """A resume node only makes sense when resuming."""
        if self.resume_node_id is not None and self.decision != AgentInterventionDecision.RESUME:
            raise ValueError("resume_node_id is only valid with decision=resume")
        return self


class ClaimAgentResumeRequest(BaseModel):
    """A runner claims an authorized resume; one claim key owns the resumed run."""

    claim_key: str = Field(min_length=1, max_length=128)


class RecordAgentResumeOutcomeRequest(BaseModel):
    """The resumed runner reports how its run ended."""

    claim_key: str = Field(min_length=1, max_length=128)
    transition: Literal["pass", "retry", "rollback", "human_escalation"]
    reason: str = Field(default="", max_length=2000)
    follow_up_intervention_id: str | None = Field(default=None, min_length=1, max_length=200)


class AgentNotificationDeliveryResponse(BaseModel):
    """Slack delivery state shown with an intervention."""

    status: AgentNotificationStatus
    attempts: int
    last_error: str
    last_attempt_at: datetime | None = None
    next_attempt_at: datetime | None = None
    channel_id: str | None = None
    message_ts: str | None = None
    sent_at: datetime | None = None
    last_reply_error: str = ""


class AgentResumeOption(BaseModel):
    """A plan node the expert may resume from, with its remaining visit budget."""

    node_id: str
    task_name: str
    visits: int
    max_visits: int | None = None
    available: bool
    reason: str = ""


class AgentInterventionResponse(BaseModel):
    """An intervention with the session state an expert needs to decide."""

    intervention_id: str
    project_id: str
    session_id: str
    chip_id: str
    idempotency_key: str
    created_by: str
    reason: AgentInterventionReason
    summary: str
    question: str
    node_id: str | None = None
    task_name: str | None = None
    qids: list[str]
    attempts: list[AgentInterventionAttempt]
    action_id: str | None = None
    previous_intervention_id: str | None = None
    checkpoint: AgentPlanCheckpoint | None = None
    plan_hash: str
    pauses_session: bool
    status: AgentInterventionStatus
    response: AgentInterventionResponseRecord | None = None
    resume_claim_key: str | None = None
    resumed_by: str | None = None
    resumed_at: datetime | None = None
    resume_outcome: AgentResumeOutcomeRecord | None = None
    notification: AgentNotificationDeliveryResponse
    events: list[AgentInterventionEvent]
    created_at: datetime
    updated_at: datetime
    session_status: AgentSessionStatus
    session_state_version: int
    session_expires_at: datetime
    actions_used: int
    max_actions: int
    can_resume: bool = Field(description="Whether an expert can authorize a resume now")
    resume_blockers: list[str] = Field(
        default_factory=list, description="Why a resume is not possible, in plain words"
    )
    resume_options: list[AgentResumeOption] = Field(default_factory=list)
    resume_command: str | None = Field(
        default=None,
        description="The client command that continues an authorized plan",
    )
    page_path: str


class ListAgentInterventionsResponse(BaseModel):
    """Interventions of one session, newest first."""

    items: list[AgentInterventionResponse]
    total: int
