"""API schemas for policy-governed local agent sessions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic resolves this runtime annotation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentAppliedQualityGate,
    AgentCandidateAcceptanceBasis,
    AgentCandidateRejection,
    AgentDecisionAssessment,
    AgentDecisionNextAction,
    AgentEvaluationMode,
    AgentInterventionAttempt,
    AgentInterventionDecision,
    AgentInterventionEvent,
    AgentInterventionReason,
    AgentInterventionResponseRecord,
    AgentInterventionStatus,
    AgentModelIdentity,
    AgentNotificationStatus,
    AgentPlanCheckpoint,
    AgentResumeOutcomeRecord,
    AgentSessionLifecycleEvent,
    AgentSessionPolicy,
    AgentSessionStatus,
    AgentSessionStopRecord,
)
from qdash.datamodel.calibration_session import CalibrationAdmission  # noqa: TC001
from qdash.datamodel.quality_metrics import RECORDED_QUALITY_METRICS

MODEL_FIELD_DESCRIPTION = (
    "The provider and model the client host reports it ran the agent with, read from the "
    "host's own runtime, never from the agent's tool arguments. Recorded as reported; QDash "
    "does not verify it, and it changes no scope or approval. Omitted when the host does not "
    "know it."
)
RECORDED_MODEL_DESCRIPTION = (
    "The model the client host reported for this record; null when none was reported. "
    "Client reported, not verified by QDash."
)


def _model_field() -> Any:
    return Field(default=None, description=MODEL_FIELD_DESCRIPTION)


def _recorded_model_field() -> Any:
    return Field(default=None, description=RECORDED_MODEL_DESCRIPTION)


class CreateAgentSessionRequest(BaseModel):
    """Create a bounded authorization session for a local agent."""

    chip_id: str = Field(min_length=1, max_length=200)
    policy: AgentSessionPolicy
    expires_in_seconds: int = Field(default=21_600, ge=60, le=86_400)
    skill_name: str = Field(default="", max_length=200)
    skill_version: str = Field(default="", max_length=200)
    skill_hash: str = Field(default="", max_length=256)
    model: AgentModelIdentity | None = _model_field()
    calibration_session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Create the session in this calibration session, which must be open, on the same "
            "chip, and created by the signed-in user. It groups the session with the "
            "objective's other work and grants nothing beyond the policy. Without it, the "
            "session joins an automatic calibration session when the server groups runs "
            "automatically, or none."
        ),
    )

    @model_validator(mode="after")
    def validate_new_quality_gates(self) -> CreateAgentSessionRequest:
        """Accept only task-scoped gates on metrics QDash records, before anything is stored.

        A session-wide gate checks results of every task, so a metric only one task reports
        rejects every other task's candidates. Sessions created before task_quality_gates
        keep their session-wide gates; a new session states each gate's task.
        """
        policy = self.policy
        if policy.evaluation is None:
            # A new session records its evaluator use; null is kept for older records only.
            self.policy = policy = policy.model_copy(update={"evaluation": AgentEvaluationMode.OFF})
        if policy.quality_gates:
            names = ", ".join(sorted(policy.quality_gates))
            raise ValueError(
                f"quality_gates ({names}) would check results of every task; new sessions "
                "name each gate's task in task_quality_gates instead, for example "
                '{"CheckRabi": {"r2": {"minimum": ...}}}'
            )
        recorded = ", ".join(sorted(RECORDED_QUALITY_METRICS))
        for task_name, gates in sorted(policy.task_quality_gates.items()):
            unknown = sorted(set(gates) - RECORDED_QUALITY_METRICS)
            if unknown:
                raise ValueError(
                    f"task_quality_gates for {task_name} names {', '.join(unknown)}, which "
                    f"QDash does not record as a quality metric (recorded: {recorded}). A "
                    "task output such as a fidelity or frequency is bounded in "
                    "allowed_overrides, and a value of another task is not evidence for "
                    "this one"
                )
        return self


class AgentSessionNotificationResponse(BaseModel):
    """Slack delivery state of one session lifecycle message."""

    event: AgentSessionLifecycleEvent
    actor: str = ""
    status: AgentNotificationStatus
    attempts: int
    last_error: str
    last_attempt_at: datetime | None = None
    next_attempt_at: datetime | None = None
    sent_at: datetime | None = None


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
    model: AgentModelIdentity | None = _recorded_model_field()
    model_name: str = Field(
        default="",
        description="provider/model_id of model, for display; empty when none was reported",
    )
    status: AgentSessionStatus
    state_version: int
    action_count: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    active_intervention_id: str | None = Field(
        default=None, description="The intervention the session waits on, if any"
    )
    start_notification: AgentSessionNotificationResponse | None = Field(
        default=None,
        description=(
            "Slack delivery of the session's start message; null for a session created "
            "before lifecycle messages existed"
        ),
    )
    end_notification: AgentSessionNotificationResponse | None = Field(
        default=None,
        description=(
            "Slack delivery of the session's end message, stored by the update that ended "
            "it; null while the session is open"
        ),
    )
    stop: AgentSessionStopRecord | None = Field(
        default=None,
        description=(
            "Who stopped the session with a stop request, why, and when; null unless a stop "
            "request ended it (an expert's stop answer is recorded on its intervention)"
        ),
    )
    calibration_session_id: str | None = Field(
        default=None,
        description="The calibration session it was created in; null when it was created alone",
    )
    calibration_admission: CalibrationAdmission | None = Field(
        default=None,
        description=(
            "Admission in its calibration session: pending (written, start not finalized; "
            "every operation is refused), admitted (operates under its policy), or rejected "
            "(the calibration session was closed first; cancelled, never operates). Null for "
            "a session created alone, which is never checked"
        ),
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
    model: AgentModelIdentity | None = _model_field()

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
    model: AgentModelIdentity | None = _recorded_model_field()


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
    applied_quality_gates: list[AgentAppliedQualityGate] = Field(
        default_factory=list,
        description=(
            "The session's quality gates this result was checked against: its task's gates "
            "and any legacy session-wide gate. Gates of other tasks are not listed."
        ),
    )
    acceptance_basis: AgentCandidateAcceptanceBasis | None = Field(
        default=None,
        description=(
            "What accepted the candidate: session_bounds (inside numeric bounds approved with "
            "the session) or task_checks (a parameter the session's update grant names, "
            "without bounds, accepted on its task's completion checks); null when rejected"
        ),
    )
    accepted: bool
    rejection: AgentCandidateRejection | None = Field(
        default=None,
        description=(
            "Why the candidate was not accepted; null when accepted. not_in_scope: the output "
            "is neither granted from this task nor bounded by the session, so it is staged for "
            "reference only; it cannot be committed from this session and is not evidence "
            "against the result or its other candidates. outside_bounds: the value is outside "
            "the session's approved bounds. quality_gate: a quality gate of the result's task "
            "failed or its metric is missing"
        ),
    )
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
    autonomous: bool = Field(
        default=False,
        description=(
            "Commit under the session's parameter_updates authority instead of a per-call "
            "approval. QDash then also requires that the signed-in user created the auto "
            "session, that its approval granted updates of this parameter from this task, "
            "that decision_id is the agent's latest pass assessment of exactly this "
            "measurement, that the measurement is the newest finished one of its task and "
            "qubit and nothing else of the session is running, that no assessment of it "
            "was fail or inconclusive, and that the stored value did not change since it "
            "was measured."
        ),
    )
    decision_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="The recorded pass decision an autonomous commit rests on",
    )

    @model_validator(mode="after")
    def validate_authority(self) -> CommitAgentCandidateRequest:
        """An autonomous commit names its assessment; a reviewed one does not."""
        if self.autonomous and self.decision_id is None:
            raise ValueError("decision_id is required for an autonomous commit")
        if not self.autonomous and self.decision_id is not None:
            raise ValueError("decision_id is only valid for an autonomous commit")
        return self


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
    autonomous: bool = Field(
        default=False,
        description=(
            "Apply under the session's parameter_updates authority instead of a per-call "
            "approval. QDash then also requires that the signed-in user created the auto "
            "session, that its approval granted apply_backend, that the commit was made "
            "under that authority in this session and is still the stored value, and that "
            "no earlier apply of it was requested. push_to_github must stay false."
        ),
    )

    @model_validator(mode="after")
    def validate_authority(self) -> ApplyAgentCandidateRequest:
        """Session authority never pushes to GitHub."""
        if self.autonomous and self.push_to_github:
            raise ValueError("an autonomous apply cannot push to GitHub")
        return self


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
    authority: Literal["reviewed", "session_policy"] = Field(
        default="reviewed",
        description=(
            "reviewed: a per-call approved commit; session_policy: committed under the "
            "session's parameter_updates authority"
        ),
    )
    decision_id: str | None = Field(
        default=None, description="The pass decision a session_policy commit rests on"
    )
    assessment_evidence: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "What QDash checked for a session_policy commit, frozen when it was reserved: the "
            "agent-reported assessment, the mechanical gates, and cited evaluations"
        ),
    )
    backend_authority: Literal["reviewed", "session_policy"] | None = Field(
        default=None, description="Authority of the backend apply request, once requested"
    )
    backend_requested_by: str | None = Field(
        default=None, description="Who requested the backend apply, once requested"
    )


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
    model: AgentModelIdentity | None = _model_field()


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
    model: AgentModelIdentity | None = _recorded_model_field()
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
    model: AgentModelIdentity | None = _model_field()


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
    model: AgentModelIdentity | None = _recorded_model_field()


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
    "client_reported",
]
AgentAuditActorKind = Literal["agent", "human", "server", "worker", "unknown"]


class StopAgentSessionRequest(BaseModel):
    """A person's request to end an agent session's authority now."""

    idempotency_key: str = Field(
        min_length=1,
        max_length=200,
        description="Key of this stop; repeating it returns the same outcome",
    )
    reason: str = Field(
        min_length=1, max_length=2000, description="Why the session is stopped, for the audit"
    )


class AgentSessionInFlightOperation(BaseModel):
    """An operation that passed the session gate before the session ended and has not settled.

    QDash does not cancel it: a measurement keeps running on the hardware and its result
    is recorded; a commit or backend apply finishes or fails on its own.
    """

    kind: Literal["measurement", "candidate_commit", "candidate_set_commit", "backend_apply"]
    id: str = Field(description="The action, commit, or candidate set commit ID")
    status: str = Field(description="Its status as QDash records it now")
    execution_id: str | None = Field(
        default=None, description="The measurement's execution, once QDash knows it"
    )


class StopAgentSessionResponse(BaseModel):
    """What a stop request did, read back from QDash's records."""

    outcome: Literal["stopped", "already_stopped", "already_ended"] = Field(
        description=(
            "stopped: this request ended the session. already_stopped: an earlier request "
            "with this key stopped it. already_ended: it had already ended another way "
            "(completed, cancelled, or expired), and this request changed nothing"
        )
    )
    session: AgentSessionResponse
    in_flight: list[AgentSessionInFlightOperation] = Field(
        default_factory=list,
        description=(
            "Operations that passed the session gate before it ended and have not settled; "
            "QDash does not cancel them"
        ),
    )
    closed_intervention_ids: list[str] = Field(
        default_factory=list,
        description="Open or resume-authorized interventions this stop closed",
    )


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
            "intervention_response, intervention_resumed, resume_outcome, or "
            "session_stopped; a calibration session's audit adds pipeline_requested, "
            "pipeline_dispatch, agent_session_linked, and session_closed"
        )
    )
    summary: str = Field(description="One readable line about the event")
    actor: str | None = Field(default=None, description="Who acted, when a record names them")
    actor_kind: AgentAuditActorKind = "unknown"
    provenance: AgentAuditProvenance = Field(
        description=(
            "server_record: QDash recorded it; server_computed: derived at read time from "
            "immutable records; agent_reported, human_reported, evaluator_reported: text "
            "that party supplied, recorded as given; client_reported: text a client sent "
            "without saying whether an agent or a person wrote it"
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
    pipeline_run_id: str | None = Field(
        default=None,
        description="The calibration session pipeline run the event belongs to, if any",
    )
    agent_session_id: str | None = Field(
        default=None,
        description=(
            "In a calibration session's audit: the agent session an event comes from. Always "
            "null in an agent session's own audit"
        ),
    )
    model: AgentModelIdentity | None = Field(
        default=None,
        description=(
            "The model the client host reported for the record behind an agent event: the "
            "session's creation, an action proposal, a decision, an agent's intervention "
            "request, or a commit made under session authority (the model of the decision it "
            "rests on). Client reported, not verified by QDash; null when none was reported, "
            "and then named in missing"
        ),
    )
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
    model: AgentModelIdentity | None = Field(
        default=None,
        description=(
            "The model the creating host reported; later events carry their own model. Client "
            "reported, not verified by QDash"
        ),
    )
    model_name: str = Field(
        default="", description="provider/model_id of model; empty when none was reported"
    )
    missing: list[str] = Field(
        default_factory=list,
        description="Identity fields the session did not record (for example model)",
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
