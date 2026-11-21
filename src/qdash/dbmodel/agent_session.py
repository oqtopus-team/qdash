"""Persistence models for policy-governed local agent sessions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Bunnet resolves this runtime annotation
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentDecisionAssessment,
    AgentDecisionNextAction,
    AgentInterventionAttempt,
    AgentInterventionEvent,
    AgentInterventionReason,
    AgentInterventionResponseRecord,
    AgentInterventionStatus,
    AgentNotificationDelivery,
    AgentPlanCheckpoint,
    AgentResumeOutcomeRecord,
    AgentSessionPolicy,
    AgentSessionStatus,
)


class AgentSessionDocument(Document):
    """Authoritative state for a bounded local-agent session."""

    session_id: str
    project_id: str
    chip_id: str
    created_by: str
    policy: AgentSessionPolicy
    skill_name: str = ""
    skill_version: str = ""
    skill_hash: str = ""
    model_name: str = ""
    status: AgentSessionStatus = AgentSessionStatus.ACTIVE
    state_version: int = 0
    action_count: int = 0
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    expires_at: datetime
    # The intervention the session waits on; set with WAITING_FOR_HUMAN.
    active_intervention_id: str | None = None
    # The response that last changed the session, so a half-applied response can be settled.
    intervention_resolution_id: str | None = None
    # The runner claim that reactivated the session after an authorized resume.
    resume_claim_key: str | None = None
    # Records of a pause, stored by the same update that paused the session and written to
    # their collections afterwards: {"intervention": {...}, "action": {...} | None}.
    pending_intervention: dict[str, Any] | None = None
    # The action record of the last submission, stored by the same update that counted it
    # and written to its collection afterwards, so a later load never sees the new state
    # version without the action it recorded.
    pending_action: dict[str, Any] | None = None
    # The one approved plan whose checkpoints this session accepts, bound by the first
    # checkpoint and updated by the pause of each later one: {"identity": {...},
    # "node_path": [...], "planner_history_lengths": {...}, "intervention_id": str}.
    plan_binding: dict[str, Any] | None = None
    # Last time an operation passed the execution gate; the gate update serializes every
    # dispatch against a pause.
    execution_gate_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "agent_sessions"
        indexes: ClassVar = [
            IndexModel([("session_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("created_at", DESCENDING),
                ]
            ),
        ]


class AgentCandidateCommitDocument(Document):
    """Audit record for a gated task-result candidate commit."""

    commit_id: str
    session_id: str
    action_id: str
    project_id: str
    idempotency_key: str
    request_hash: str
    execution_id: str
    task_id: str
    task_name: str
    chip_id: str = ""
    qid: str
    parameter_name: str
    value: float
    status: str = "committing"
    reason: str = ""
    before_snapshot: dict[str, Any] | None = None
    after_snapshot: dict[str, Any] | None = None
    committed_by: str
    state_version_before: int
    state_version_after: int
    created_at: datetime = Field(default_factory=now)
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
    backend_apply_idempotency_key: str | None = None
    backend_apply_request_hash: str | None = None
    backend_push_to_github: bool = False
    backend_requested_at: datetime | None = None
    backend_applied_at: datetime | None = None
    # Reservation of one backend apply dispatch; unconfirmed until it passed the session gate.
    backend_dispatch_token: str | None = None
    backend_dispatch_confirmed: bool | None = None

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "agent_candidate_commits"
        indexes: ClassVar = [
            IndexModel([("commit_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("action_id", ASCENDING),
                    ("created_at", ASCENDING),
                ]
            ),
        ]


class AgentCandidateSetCommitDocument(Document):
    """Audit record for one same-qubit candidate-set commit."""

    commit_id: str
    session_id: str
    project_id: str
    idempotency_key: str
    request_hash: str
    chip_id: str
    qid: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "committing"
    reason: str = ""
    before_snapshot: dict[str, Any] = Field(default_factory=dict)
    after_snapshot: dict[str, Any] = Field(default_factory=dict)
    committed_by: str
    state_version_before: int
    state_version_after: int
    created_at: datetime = Field(default_factory=now)
    committed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "agent_candidate_set_commits"
        indexes: ClassVar = [
            IndexModel([("commit_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
            ),
        ]


class AgentActionDocument(Document):
    """Immutable audit record for one local-agent action proposal."""

    action_id: str
    session_id: str
    project_id: str
    idempotency_key: str
    request_hash: str
    action_type: AgentActionType
    task_name: str | None = None
    qids: list[str] = Field(default_factory=list)
    parameter_overrides: dict[str, float] = Field(default_factory=dict)
    diagnosis: str = ""
    decision: AgentActionDecision
    reason: str
    execution_status: str = "not_started"
    operation_id: str | None = None
    execution_id: str | None = None
    state_version_before: int
    state_version_after: int
    created_at: datetime = Field(default_factory=now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Reservation of one dispatch; unconfirmed until it passed the session gate.
    dispatch_token: str | None = None
    dispatch_confirmed: bool | None = None
    dispatch_reserved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "agent_actions"
        indexes: ClassVar = [
            IndexModel([("action_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("created_at", ASCENDING),
                ]
            ),
        ]


class AgentInterventionDocument(Document):
    """Durable record of an agent stopping for a person, and of the person's answer.

    QDash is the source of truth for the intervention; Slack only points to it. The record
    keeps references to actions, executions, task results, and evaluations, not log output.
    """

    intervention_id: str
    project_id: str
    session_id: str
    chip_id: str
    idempotency_key: str
    request_hash: str
    created_by: str
    reason: AgentInterventionReason
    summary: str
    question: str
    node_id: str | None = None
    task_name: str | None = None
    qids: list[str] = Field(default_factory=list)
    attempts: list[AgentInterventionAttempt] = Field(default_factory=list)
    action_id: str | None = None
    previous_intervention_id: str | None = None
    checkpoint: AgentPlanCheckpoint | None = None
    plan_hash: str = ""
    pauses_session: bool = False
    session_status_at_open: AgentSessionStatus
    session_state_version_at_open: int
    status: AgentInterventionStatus = AgentInterventionStatus.OPEN
    response: AgentInterventionResponseRecord | None = None
    responding_since: datetime | None = None
    resume_claim_key: str | None = None
    resumed_by: str | None = None
    resumed_at: datetime | None = None
    resume_outcome: AgentResumeOutcomeRecord | None = None
    notification: AgentNotificationDelivery = Field(default_factory=AgentNotificationDelivery)
    events: list[AgentInterventionEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "agent_interventions"
        indexes: ClassVar = [
            IndexModel([("intervention_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("created_at", DESCENDING),
                ]
            ),
            IndexModel(
                [
                    ("notification.status", ASCENDING),
                    ("notification.next_attempt_at", ASCENDING),
                ]
            ),
        ]


class AgentDecisionDocument(Document):
    """Append-only record of one agent decision: its reading of the evidence and its next step.

    The interpretation, assessment, and next action are what the agent reported. The evidence
    snapshot is what QDash read from its own records when the decision was recorded, so later
    status changes of those records do not rewrite it. A correction is a new record that names
    the one it supersedes; records are never updated.
    """

    decision_id: str
    project_id: str
    session_id: str
    chip_id: str
    idempotency_key: str
    request_hash: str
    recorded_by: str
    recorded_at: datetime = Field(default_factory=now)
    session_status_at_record: str
    session_state_version_at_record: int
    assessment: AgentDecisionAssessment | None = None
    interpretation: str
    next_action: AgentDecisionNextAction
    next_detail: str = ""
    evidence_action_ids: list[str] = Field(default_factory=list)
    evaluation_ids: list[str] = Field(default_factory=list)
    next_action_id: str | None = None
    intervention_id: str | None = None
    supersedes_decision_id: str | None = None
    # Frozen server-side reading of the cited records: {"actions": [...], "evaluations": [...]}.
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    # The record's place in the session's decision quota, 0 up to the quota minus one. The
    # unique index on it makes the quota check and the insert one atomic write: two
    # concurrent recordings cannot take the same slot, so a session never holds more.
    quota_slot: int

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "agent_decisions"
        indexes: ClassVar = [
            IndexModel([("decision_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("recorded_at", ASCENDING),
                ]
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("session_id", ASCENDING),
                    ("quota_slot", ASCENDING),
                ],
                unique=True,
            ),
        ]
