"""Domain models for policy-governed local agent sessions."""

from __future__ import annotations

import math
from enum import Enum

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


class AgentActionDecision(str, Enum):
    """Platform authorization decision for an action proposal."""

    AUTHORIZED = "authorized"
    REJECTED = "rejected"


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
