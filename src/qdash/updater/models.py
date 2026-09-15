"""Models shared by the host-side updater endpoints."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class UpdateState(StrEnum):
    """Lifecycle state for one update operation."""

    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    ROLLING_BACK = "rolling_back"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class UpdateManifest(BaseModel):
    """Release-owned declaration that unattended source updates are supported."""

    schema_version: Literal[1] = 1
    automatic_update: bool = False
    migration_mode: str = "manual"
    notes: str = ""


class UpdateStatus(BaseModel):
    """Current installation and latest stable release status."""

    enabled: bool = True
    current_version: str
    current_commit: str
    latest_version: str | None = None
    update_available: bool = False
    can_update: bool = False
    dirty: bool = False
    blocked_reason: str | None = None
    operation_id: str | None = None
    operation_state: UpdateState = UpdateState.IDLE
    checked_at: datetime


class StartUpdateRequest(BaseModel):
    """Request to install the latest stable release."""

    expected_current_version: str | None = None
    operation_id: str | None = None


class UpdateOperation(BaseModel):
    """Persisted progress for one update operation."""

    operation_id: str
    state: UpdateState
    source_version: str
    target_version: str
    stage: str
    message: str
    progress: int = Field(ge=0, le=100)
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    previous_commit: str | None = None
    log_tail: list[str] = Field(default_factory=list)
