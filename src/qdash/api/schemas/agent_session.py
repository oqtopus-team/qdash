"""API schemas for policy-governed local agent sessions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic resolves this runtime annotation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentDecisionAssessment,
    AgentDecisionNextAction,
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


class ListAgentSessionsResponse(BaseModel):
    """Agent sessions of the current project, newest first."""

    items: list[AgentSessionResponse]
    total: int = Field(description="Number of sessions returned, after filters and the limit")


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
    autonomous: bool = Field(
        default=False,
        description=(
            "The proposal is an autonomous step that runs without a per-call approval. QDash "
            "then also requires that the signed-in user created the session, that its "
            "autonomy is auto, that no measurement of the session is running, that an "
            "undispatched identical action is dispatched instead, that the task and qubit "
            "stay within max_rounds_per_target, and that a finished identical measurement "
            "is repeated only with repeat_of_action_id. A refused step is not recorded and "
            "uses no action budget. Only valid for run_task."
        ),
    )
    repeat_of_action_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="The finished identical action an autonomous step measures again on purpose",
    )

    @model_validator(mode="after")
    def validate_action_shape(self) -> SubmitAgentActionRequest:
        """Require task details only for run-task proposals."""
        if self.repeat_of_action_id is not None and not self.autonomous:
            raise ValueError("repeat_of_action_id is only valid for autonomous proposals")
        if self.autonomous and self.action_type != AgentActionType.RUN_TASK:
            raise ValueError("autonomous is only valid for run_task")
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
    autonomous: bool = Field(
        default=False,
        description="Whether QDash authorized the action as an autonomous step",
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
    autonomous: bool = Field(
        default=False,
        description=(
            "The dispatch is an autonomous step. QDash then also requires that the signed-in "
            "user created the session, that its autonomy is auto, and that no other "
            "measurement of the session is being dispatched or running."
        ),
    )

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
    autonomous: bool = Field(
        default=False,
        description=(
            "The request comes from an autonomous agent without a per-call approval. QDash "
            "then also requires that the signed-in user created the session and that its "
            "autonomy is auto. Who may answer the intervention does not change."
        ),
    )


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


def _reference_list(description: str) -> Any:
    return Field(
        default_factory=list,
        max_length=20,
        description=description,
    )


class RecordAgentDecisionRequest(BaseModel):
    """Record the agent's reading of a result and the step it chose next.

    The text fields are the agent's own concise statements, recorded as reported. QDash checks
    that every referenced action, evaluation, intervention, and decision belongs to the session
    and freezes what its records say about the cited evidence.
    """

    idempotency_key: str = Field(min_length=1, max_length=128)
    assessment: AgentDecisionAssessment | None = Field(
        default=None, description="How the agent judged the evidence; omitted when not stated"
    )
    interpretation: str = Field(
        min_length=1,
        max_length=2000,
        description="Concise reasoning the agent states for the decision, citing the evidence",
    )
    next_action: AgentDecisionNextAction
    next_detail: str = Field(default="", max_length=500, description="The chosen next step")
    evidence_action_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = (
        _reference_list("Actions of this session whose results the decision reads")
    )
    evaluation_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = _reference_list(
        "Evaluations of those actions' task results"
    )
    next_action_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="The action of this session that carries out the next step, when one exists",
    )
    intervention_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="The intervention of this session the decision opened or acts on",
    )
    supersedes_decision_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="An earlier decision of this session that this record corrects",
    )


class AgentDecisionResponse(BaseModel):
    """One recorded agent decision with QDash's frozen reading of its evidence."""

    decision_id: str
    session_id: str
    project_id: str
    chip_id: str
    idempotency_key: str
    recorded_by: str
    recorded_at: datetime
    session_status_at_record: str
    session_state_version_at_record: int
    assessment: AgentDecisionAssessment | None = None
    interpretation: str
    next_action: AgentDecisionNextAction
    next_detail: str
    evidence_action_ids: list[str]
    evaluation_ids: list[str]
    next_action_id: str | None = None
    intervention_id: str | None = None
    supersedes_decision_id: str | None = None
    evidence_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="What QDash's records said about the cited evidence when it was recorded",
    )


class ListAgentDecisionsResponse(BaseModel):
    """Decisions of one session, oldest first."""

    items: list[AgentDecisionResponse]
    total: int


AgentAuditProvenance = Literal[
    "server_record",
    "server_computed",
    "agent_reported",
    "human_reported",
    "evaluator_reported",
]
AgentAuditActorKind = Literal["agent", "human", "server", "worker", "unknown"]


class AgentAuditEvent(BaseModel):
    """One entry of a session's experiment audit timeline, built from QDash's own records."""

    event_id: str = Field(description="Stable identifier: <kind>:<source record id>")
    sequence: int = Field(description="Position in the session's full timeline, from 0")
    at: datetime = Field(description="When the event happened, as its source record says")
    state_version: int = Field(
        description=(
            "Session state version the event belongs to: recorded by its source record, or "
            "inherited from its action or commit. Orders events that share a timestamp."
        )
    )
    kind: str = Field(
        description=(
            "session_created, action_proposed, measurement, evaluation, decision, "
            "candidate_commit, candidate_set_commit, backend_apply, intervention_opened, "
            "intervention_response, intervention_resumed, or resume_outcome"
        )
    )
    summary: str = Field(description="One readable line about the event")
    actor: str | None = Field(default=None, description="Who acted, when a record names them")
    actor_kind: AgentAuditActorKind = "unknown"
    provenance: AgentAuditProvenance = Field(
        description=(
            "server_record: QDash recorded it; server_computed: derived at read time from "
            "immutable records; agent_reported, human_reported, evaluator_reported: text "
            "that party supplied, recorded as given"
        )
    )
    status: str | None = Field(default=None, description="Status of the source record")
    status_is_current: bool = Field(
        default=False,
        description="Whether status is the source record's live status rather than frozen",
    )
    action_id: str | None = None
    execution_id: str | None = None
    task_id: str | None = None
    task_name: str | None = None
    qid: str | None = None
    commit_id: str | None = None
    evaluation_id: str | None = None
    intervention_id: str | None = None
    decision_id: str | None = None
    missing: list[str] = Field(
        default_factory=list,
        description="Facts the records do not hold for this event; never filled in",
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="Kind-specific details; see the developer guide"
    )


class AgentAuditSessionHeader(BaseModel):
    """Who and what a session's audit belongs to."""

    session_id: str
    project_id: str
    chip_id: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    status: AgentSessionStatus
    state_version: int
    action_count: int
    policy: AgentSessionPolicy
    skill_name: str
    skill_version: str
    skill_hash: str
    model_name: str
    missing: list[str] = Field(
        default_factory=list,
        description="Identity fields the session did not record (for example model_name)",
    )


class AgentSessionAuditResponse(BaseModel):
    """A page of one snapshot of a session's chronological experiment audit, or all of it.

    A snapshot contains two matching projected reads, not an atomic point-in-time database
    view. Changes that revert between reads can go undetected. Pagination is bound to the
    fingerprint of that projected content. Read a new first page or export for later records.
    """

    schema_version: Literal["qdash.agent-session-audit.v1"] = "qdash.agent-session-audit.v1"
    generated_at: datetime
    snapshot_id: str = Field(
        description=(
            "Fingerprint of the snapshot this response belongs to; every page of one cursor "
            "chain carries the same value"
        )
    )
    session: AgentAuditSessionHeader
    events: list[AgentAuditEvent]
    total_events: int = Field(description="Events in the snapshot")
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Pass as cursor to read the next page of the same snapshot. The read is refused "
            "with 409 when the records changed since the snapshot; then start again without a "
            "cursor"
        ),
    )
    complete: bool = Field(
        description=(
            "Whether this response ends the snapshot: with the earlier pages of the same "
            "snapshot_id it holds every event of the snapshot"
        )
    )
    notes: list[str] = Field(
        default_factory=list, description="What the audit does and does not contain"
    )
