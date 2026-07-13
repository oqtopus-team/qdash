"""API schemas for policy-governed local agent sessions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic resolves this runtime annotation
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
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


class ListAgentActionsResponse(BaseModel):
    """Ordered audit records for one agent session."""

    items: list[AgentActionResponse]
    total: int


class ExecuteAgentActionRequest(BaseModel):
    """Dispatch one authorized run-task action as a staged measurement."""

    source_execution_id: str = Field(min_length=1, max_length=200)
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
