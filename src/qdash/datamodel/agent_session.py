"""Domain models for policy-governed local agent sessions."""

from __future__ import annotations

import math
from datetime import datetime  # noqa: TC003 - Pydantic resolves this runtime annotation
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgentSessionStatus(str, Enum):
    """Lifecycle state of an agent session."""

    ACTIVE = "active"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AgentActionType(str, Enum):
    """Actions that a local agent may propose to QDash."""

    RUN_TASK = "run_task"
    REQUEST_HUMAN = "request_human"
    COMPLETE_SESSION = "complete_session"


class AgentInterventionReason(str, Enum):
    """Why an agent stopped and asked a person for help."""

    UNKNOWN_OUTCOME = "unknown_outcome"  # a status or result no known recovery covers
    RECOVERY_EXHAUSTED = "recovery_exhausted"  # retries, rounds, or the node budget ran out
    EVALUATION_FAILED = "evaluation_failed"  # the evaluation failed or its fit was unreliable
    PLATFORM_ERROR = "platform_error"  # QDash, the workflow, or the hardware reported an error
    POLICY_LIMIT = "policy_limit"  # the session scope, budget, or expiry stops the plan
    AGENT_REQUEST = "agent_request"  # the agent or the task knowledge asked for a person


class AgentInterventionStatus(str, Enum):
    """Lifecycle of one human intervention.

    ``open`` waits for an expert. ``responding`` is the short window while a response is
    being applied to the session. ``resume_authorized`` means an expert allowed the runner to
    continue but no runner has claimed it yet; ``resumed`` means a runner claimed it and the
    session is active again. ``stopped`` means the expert ended the session. ``discarded``
    marks a request that never paused its session.
    """

    OPEN = "open"
    RESPONDING = "responding"
    RESUME_AUTHORIZED = "resume_authorized"
    RESUMED = "resumed"
    STOPPED = "stopped"
    DISCARDED = "discarded"


class AgentInterventionDecision(str, Enum):
    """What the expert decided for the paused session."""

    RESUME = "resume"
    STOP = "stop"


class AgentNotificationStatus(str, Enum):
    """Delivery state of the Slack root message for one intervention."""

    DISABLED = "disabled"  # Slack agent notifications are not configured
    PENDING = "pending"  # waiting for the first or next attempt
    SENDING = "sending"  # an attempt holds the lease
    SENT = "sent"
    FAILED = "failed"  # automatic attempts are used up; an explicit retry is needed


class AgentAutonomy(str, Enum):
    """How much of a plan the agent may run without a person confirming each step."""

    CONFIRM_EACH = "confirm_each"  # every measurement is confirmed by a person (default)
    AUTO = "auto"  # the plan, bounds, and budget are confirmed once; steps follow the evaluation


class AgentActionDecision(str, Enum):
    """Platform authorization decision for an action proposal."""

    AUTHORIZED = "authorized"
    REJECTED = "rejected"


class AgentDecisionAssessment(str, Enum):
    """How the agent judged the evidence a decision cites; reported by the agent."""

    PASS = "pass"  # noqa: S105 - an assessment, not a credential; meets the criteria
    FAIL = "fail"  # the result or the measurement failed the criteria
    INCONCLUSIVE = "inconclusive"  # the evidence does not settle it


class AgentDecisionNextAction(str, Enum):
    """What the agent decided to do next; a stated intent, not an execution."""

    NEXT_TASK = "next_task"  # move on to the next task of the goal
    REPEAT = "repeat"  # measure again with identical settings
    ADJUST_AND_RETRY = "adjust_and_retry"  # measure again with changed inputs
    ROLLBACK = "rollback"  # return to an earlier task
    PROPOSE_COMMIT = "propose_commit"  # propose committing an accepted candidate
    REQUEST_HUMAN = "request_human"  # stop and ask an expert
    SKIP_TARGET = "skip_target"  # leave the qubit out of later steps
    COMPLETE = "complete"  # the goal is reached
    STOP = "stop"  # end without reaching the goal


class NumericBounds(BaseModel):
    """Inclusive numeric bounds for one agent-controlled parameter."""

    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_order(self) -> NumericBounds:
        """Require a non-empty, ordered interval."""
        if self.minimum is None and self.maximum is None:
            raise ValueError("at least one of minimum or maximum is required")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must be less than or equal to maximum")
        return self

    def contains(self, value: float) -> bool:
        """Return whether a value is within the configured interval."""
        if not math.isfinite(value):
            return False
        if self.minimum is not None and value < self.minimum:
            return False
        return not (self.maximum is not None and value > self.maximum)


class AgentSessionPolicy(BaseModel):
    """Immutable scope authorized by a user for one agent session."""

    qids: list[str] = Field(min_length=1)
    allowed_tasks: list[str] = Field(min_length=1)
    allowed_actions: list[AgentActionType] = Field(
        default_factory=lambda: [
            AgentActionType.RUN_TASK,
            AgentActionType.REQUEST_HUMAN,
            AgentActionType.COMPLETE_SESSION,
        ],
        min_length=1,
    )
    allowed_overrides: dict[str, NumericBounds] = Field(default_factory=dict)
    quality_gates: dict[str, NumericBounds] = Field(default_factory=dict)
    allow_reconfigure: bool = False
    max_actions: int = Field(default=100, ge=1, le=10_000)
    autonomy: AgentAutonomy = Field(
        default=AgentAutonomy.CONFIRM_EACH,
        description="auto lets a plan choose its next step from the evaluation without a person",
    )
    max_rounds_per_target: int = Field(
        default=3,
        ge=1,
        le=20,
        description="How many times an autonomous plan may run the same node on one target",
    )


def _id_field() -> Any:
    return Field(min_length=1, max_length=200)


def _optional_id_field() -> Any:
    return Field(default=None, min_length=1, max_length=200)


class AgentInterventionAttempt(BaseModel):
    """One recent attempt shown to the expert, as references rather than log output."""

    node_id: str = Field(default="", max_length=200)
    task_name: str = Field(default="", max_length=200)
    qid: str = Field(default="", max_length=200)
    transition: str = Field(default="", max_length=64)
    status: str = Field(default="", max_length=200, description="Evaluation or execution status")
    reason: str = Field(default="", max_length=1000)
    action_id: str | None = _optional_id_field()
    execution_id: str | None = _optional_id_field()
    task_id: str | None = _optional_id_field()
    evaluation_id: str | None = _optional_id_field()
    evaluation_run_id: str | None = _optional_id_field()


class AgentPlanCheckpointNode(BaseModel):
    """One node of the approved plan, as the runner received it."""

    id: str = _id_field()
    task_name: str = _id_field()
    candidate_parameter: str = _id_field()
    on_pass: str | None = _optional_id_field()
    on_rollback: str | None = _optional_id_field()
    parameter_overrides: dict[str, float] = Field(default_factory=dict)
    diagnosis: str = Field(default="", max_length=2000)
    reconfigure_before_task: bool = False
    commit_candidate: bool = False
    apply_backend: bool = False
    push_to_github: bool = False

    @model_validator(mode="after")
    def validate_overrides(self) -> AgentPlanCheckpointNode:
        """Reject non-finite overrides."""
        if any(not math.isfinite(value) for value in self.parameter_overrides.values()):
            raise ValueError("plan parameter overrides must be finite")
        return self


class AgentCheckpointCandidate(BaseModel):
    """An accepted candidate the plan carries; the runner re-reads its value from QDash."""

    action_id: str = _id_field()
    parameter_name: str = _id_field()
    task_id: str = _id_field()


class AgentPlannerVerdictRecord(BaseModel):
    """One evaluation verdict the planner remembers for its stop rules."""

    status: str = Field(max_length=200)
    fit_reliability: str | None = Field(default=None, max_length=64)
    evaluation_id: str = Field(default="", max_length=200)


class AgentPlanCheckpoint(BaseModel):
    """Where a stopped plan was, so a runner can continue it without repeating work.

    The checkpoint holds the approved plan, the idempotency prefix, and every counter the
    plan's bounds use. QDash does not take the counters on trust: it binds a session to the
    plan of its first checkpoint and rejects a checkpoint that changes the plan, its prefix,
    or its bounds, shortens the recorded path, or reports fewer node visits than the
    session's run_task actions show.
    """

    version: int = Field(default=1, ge=1, le=1)
    qid: str = _id_field()
    source_execution_id: str | None = _optional_id_field()
    nodes: list[AgentPlanCheckpointNode] = Field(min_length=1, max_length=50)
    idempotency_prefix: str = Field(min_length=1, max_length=96)
    node_path: list[str] = Field(default_factory=list, max_length=1000)
    visit_counts: dict[str, int] = Field(default_factory=dict)
    stopped_node_id: str = _id_field()
    accepted_candidates: list[AgentCheckpointCandidate] = Field(
        default_factory=list, max_length=100
    )
    max_pre_dispatch_retries: int = Field(default=1, ge=0, le=10)
    max_node_executions: int = Field(ge=1, le=10_000)
    max_node_visits: int | None = Field(default=None, ge=1, le=10_000)
    commit_on_success: bool = False
    planner: str = Field(default="none", pattern="^(none|evaluation)$")
    planner_history: dict[str, list[AgentPlannerVerdictRecord]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph_references(self) -> AgentPlanCheckpoint:
        """Every recorded node id must be a node of the plan."""
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("checkpoint node ids must be unique")
        known = set(node_ids)
        unknown = (
            {node_id for node_id in self.node_path if node_id not in known}
            | {node_id for node_id in self.visit_counts if node_id not in known}
            | {node_id for node_id in self.planner_history if node_id not in known}
        )
        if self.stopped_node_id not in known:
            unknown.add(self.stopped_node_id)
        if unknown:
            raise ValueError(f"checkpoint names unknown nodes: {', '.join(sorted(unknown))}")
        if any(count < 0 for count in self.visit_counts.values()):
            raise ValueError("checkpoint visit counts must be non-negative")
        if any(len(history) > 50 for history in self.planner_history.values()):
            raise ValueError("checkpoint planner history is limited to 50 verdicts per node")
        return self


class AgentInterventionResponseRecord(BaseModel):
    """The expert's recorded answer. Guidance is evidence for the agent, never a command."""

    response_id: str
    idempotency_key: str = ""
    decision: AgentInterventionDecision
    guidance: str = Field(default="", max_length=5000)
    resume_node_id: str | None = None
    responded_by: str
    responded_at: datetime
    expected_state_version: int


class AgentResumeOutcomeRecord(BaseModel):
    """What the resumed runner reported when its run ended."""

    transition: str = Field(max_length=64)
    reason: str = Field(default="", max_length=2000)
    follow_up_intervention_id: str | None = None
    recorded_by: str
    recorded_at: datetime


class AgentNotificationDelivery(BaseModel):
    """Slack delivery state of an intervention's root message and thread replies."""

    status: AgentNotificationStatus = AgentNotificationStatus.DISABLED
    attempts: int = 0
    last_error: str = ""
    last_attempt_at: datetime | None = None
    next_attempt_at: datetime | None = None
    lease_until: datetime | None = None
    channel_id: str | None = None
    message_ts: str | None = None
    sent_at: datetime | None = None
    last_reply_error: str = ""


class AgentInterventionEvent(BaseModel):
    """One audit entry: who did what to the intervention, and when."""

    at: datetime
    actor: str
    kind: str
    detail: str = ""
