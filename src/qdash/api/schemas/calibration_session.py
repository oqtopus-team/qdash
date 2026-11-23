"""API schemas for calibration sessions: one objective, its pipeline runs and agent sessions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - pydantic resolves this runtime annotation

from pydantic import BaseModel, Field

from qdash.api.schemas.execution import (  # noqa: TC001 - pydantic field types
    ExecutionResponseSummary,
    PipelineProgress,
)
from qdash.datamodel.agent_session import (  # noqa: TC001 - pydantic field types
    AgentAutonomy,
    AgentSessionStatus,
)
from qdash.datamodel.calibration_session import (  # noqa: TC001 - pydantic field types
    CalibrationAdmission,
    CalibrationChildReservation,
    CalibrationPipelineRunStatus,
    CalibrationSessionStatus,
)
from qdash.datamodel.launch_origin import ReportedLaunchOrigin  # noqa: TC001 - pydantic field


class CreateCalibrationSessionRequest(BaseModel):
    """Start a calibration session for one objective on one chip."""

    chip_id: str = Field(min_length=1, max_length=200)
    objective: str = Field(
        min_length=1,
        max_length=500,
        description="What the calibration is for, in a person's words; shown with every run",
    )


class CloseCalibrationSessionRequest(BaseModel):
    """End work on a calibration session's objective."""

    closing_note: str = Field(
        default="",
        max_length=2000,
        description="What the person closing it wants recorded; QDash does not judge the outcome",
    )
    acknowledge_unknown_runs: bool = Field(
        default=False,
        description=(
            "Close although some pipeline runs have an unknown dispatch outcome, or some agent "
            "session starts were reserved long ago and never recorded, after checking the "
            "Execution list and the agent sessions for them. They are recorded with the closure. "
            "Such a pipeline run was admitted: it may be running or may still start after the "
            "close, which does not cancel it. Such an agent session was never admitted: if it "
            "is recorded later it is rejected and never operates."
        ),
    )


class CalibrationSessionResponse(BaseModel):
    """A calibration session record."""

    calibration_session_id: str
    project_id: str
    chip_id: str
    objective: str
    created_by: str = Field(description="The signed-in user who created it")
    status: CalibrationSessionStatus
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    closed_by: str | None = None
    closing_note: str = ""
    closed_with_unknown_runs: list[str] = Field(
        default_factory=list,
        description="Pipeline runs whose dispatch outcome was unknown when it was closed",
    )
    closed_with_unknown_starts: list[CalibrationChildReservation] = Field(
        default_factory=list,
        description=(
            "Agent session starts reserved long ago and never recorded when it was closed. One "
            "recorded later is rejected (calibration_admission: rejected) and never operates."
        ),
    )


class ListCalibrationSessionsResponse(BaseModel):
    """Calibration sessions of the current project, newest first."""

    items: list[CalibrationSessionResponse]
    total: int = Field(description="Number of sessions returned, after filters and the limit")
    skip: int = Field(default=0, description="Sessions skipped before the first one returned")
    has_more: bool = Field(
        default=False, description="True when more sessions match after the ones returned"
    )


class CalibrationPipelineRunResponse(BaseModel):
    """One pipeline run requested in a calibration session, with its step executions."""

    run_id: str
    calibration_session_id: str
    chip_id: str
    idempotency_key: str
    requested_by: str
    reported_origin: ReportedLaunchOrigin | None = Field(
        default=None,
        description=(
            "How the caller said it started the run (client reported, not verified); null when "
            "nothing was reported, as for a run requested directly"
        ),
    )
    dispatch_status: CalibrationPipelineRunStatus = Field(
        description=(
            "Whether QDash launched the run: dispatching, dispatched, rejected (nothing was "
            "started), or unknown (it may have started; check the Execution list)"
        )
    )
    attempts: int
    pipeline_name: str
    backend_name: str
    flow_run_id: str | None = None
    execution_id: str | None = Field(
        default=None, description="The first step's execution, as returned at dispatch"
    )
    error: str = ""
    requested_at: datetime
    updated_at: datetime
    pipeline: PipelineProgress | None = Field(
        default=None,
        description=(
            "The run as a whole, from its step executions; null until its first execution exists"
        ),
    )
    executions: list[ExecutionResponseSummary] = Field(
        default_factory=list,
        description="Every execution of the run's flow run on the chip, oldest first",
    )


class CalibrationAgentSessionChild(BaseModel):
    """An agent session created in a calibration session, with the executions it dispatched."""

    session_id: str
    status: AgentSessionStatus = Field(description="Its own status, with expiry applied")
    created_by: str
    created_at: datetime
    expires_at: datetime
    autonomy: AgentAutonomy
    qids: list[str]
    allowed_tasks: list[str]
    action_count: int
    active_intervention_id: str | None = None
    model_name: str = ""
    calibration_admission: CalibrationAdmission | None = Field(
        default=None,
        description=(
            "pending until its start is finalized, admitted after, rejected when the session "
            "was closed first; it operates only when admitted"
        ),
    )
    executions: list[ExecutionResponseSummary] = Field(
        default_factory=list,
        description="Executions its actions dispatched, as the agent session links them",
    )


class CalibrationSessionDetailResponse(CalibrationSessionResponse):
    """A calibration session with every run started in it."""

    pipeline_runs: list[CalibrationPipelineRunResponse] = Field(
        default_factory=list,
        description="The most recent pipeline runs (at most 100), oldest first",
    )
    pipeline_run_total: int = Field(
        default=0,
        description="Every pipeline run requested in it; more than listed when the list is cut",
    )
    agent_sessions: list[CalibrationAgentSessionChild] = Field(
        default_factory=list,
        description="The most recent agent sessions (at most 100), oldest first",
    )
    agent_session_total: int = Field(
        default=0,
        description="Every agent session created in it; more than listed when the list is cut",
    )
    close_blockers: list[str] = Field(
        default_factory=list,
        description=(
            "Why it cannot be closed now, read from every child (not only the listed ones): "
            "runs and agent sessions that still run or wait, operations an ended agent session "
            "has not settled, and children being started. Empty when closing is allowed."
        ),
    )
    unknown_runs: list[str] = Field(
        default_factory=list,
        description=(
            "Pipeline runs whose dispatch outcome is unknown. Each was admitted, so it may be "
            "running or may still start, even after the session is closed"
        ),
    )
    unknown_starts: list[CalibrationChildReservation] = Field(
        default_factory=list,
        description=(
            "Agent session starts reserved long ago whose session was never recorded; the "
            "request may have stopped or may still record it. One recorded after a close is "
            "rejected and never operates"
        ),
    )
