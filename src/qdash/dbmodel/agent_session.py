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
    AgentSessionPolicy,
    AgentSessionStatus,
)


class AgentSessionDocument(Document):
    """Authoritative state for a bounded local-agent campaign."""

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


class AgentCampaignCommitDocument(Document):
    """Audit record for one same-qubit campaign candidate-set commit."""

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

        name = "agent_campaign_commits"
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
