"""Schemas for administrator-controlled QDash system updates."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SystemUpdateState(StrEnum):
    """Lifecycle state returned by the host updater."""

    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    ROLLING_BACK = "rolling_back"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class SystemUpdateStatusResponse(BaseModel):
    """Current installation and latest stable release status."""

    enabled: bool
    current_version: str
    current_commit: str
    latest_version: str | None = None
    update_available: bool = False
    can_update: bool = False
    dirty: bool = False
    blocked_reason: str | None = None
    operation_id: str | None = None
    operation_state: SystemUpdateState = SystemUpdateState.IDLE
    checked_at: datetime


class StartSystemUpdateRequest(BaseModel):
    """Start request guarded against stale status screens."""

    expected_current_version: str | None = None


class SystemUpdateOperationResponse(BaseModel):
    """Progress for one updater-owned operation."""

    operation_id: str
    state: SystemUpdateState
    source_version: str
    target_version: str
    stage: str
    message: str
    progress: int = Field(ge=0, le=100)
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    log_tail: list[str] = Field(default_factory=list)
