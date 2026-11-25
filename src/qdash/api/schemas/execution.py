"""Schema definitions for execution router."""

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from qdash.common.utils.datetime import format_elapsed_time, parse_elapsed_time
from qdash.datamodel.agent_session import AgentSessionStatus
from qdash.datamodel.calibration_session import CalibrationSessionStatus
from qdash.datamodel.launch_origin import ReportedLaunchOrigin
from qdash.datamodel.step_record import TransformStepRecord
from qdash.datamodel.task import TaskResultInputParameter, TaskResultOutputParameter
from qdash.datamodel.task_invocation import TaskInvocation


class ArtifactPreviewResponse(BaseModel):
    """Tabular preview of a NetCDF calibration artifact."""

    filename: str
    target: str | None = None
    source_type: str | None = None
    shape: list[int]
    dtype: str
    columns: list[str]
    rows: list[dict[str, int | float | str | bool | None]]
    total_rows: int
    truncated: bool


class ExecutionLockStatusResponse(BaseModel):
    """Response model for the fetch_execution_lock_status endpoint."""

    lock: bool
    execution_id: str | None = None
    chip_id: str | None = None
    name: str | None = None
    status: str | None = None


class ExecutionAvailabilityRequest(BaseModel):
    """Targets to check without reserving hardware or creating an execution."""

    flow_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ExecutionAvailabilityResponse(BaseModel):
    """Current resource availability; execution admission still checks atomically."""

    available: bool
    reason: str | None = None


class Task(BaseModel):
    """Task is a Pydantic model that represents a task."""

    user_id: str | None = None
    username: str = ""
    task_id: str | None = None
    qid: str | None = None
    name: str = ""  # Default empty string for name
    upstream_id: str | None = None
    status: str = "pending"  # Default status
    message: str | None = None
    input_parameters: dict[str, TaskResultInputParameter] | None = None
    output_parameters: dict[str, TaskResultOutputParameter] | None = None
    output_parameter_names: list[str] | None = None
    run_parameters: dict[str, Any] | None = None
    note: dict[str, Any] | None = None
    figure_path: list[str] | None = None
    json_figure_path: list[str] | None = None
    raw_data_path: list[str] | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    task_type: str | None = None
    invocation: TaskInvocation | None = Field(
        default=None,
        description="Planned step and call this result executed; null for older results.",
    )
    default_view: bool = True

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats."""
        return parse_elapsed_time(v)

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None


class ExecutionAgentSessionLink(BaseModel):
    """The agent session an execution belongs to, as its records establish it."""

    session_id: str
    linked: bool = Field(
        description=(
            "True when an action of the session dispatched this execution on the same chip; "
            "false when only a tag names the session, which is no authority to group it"
        )
    )
    action_id: str | None = None
    status: AgentSessionStatus | None = Field(
        default=None, description="The session's state, when the session is in this project"
    )
    created_by: str | None = Field(
        default=None,
        description=(
            "The user who created the session and is responsible for it; set only when linked. "
            "Answers, resumes, and commit authorizations are recorded separately in the audit"
        ),
    )
    model_name: str = Field(
        default="",
        description=(
            "provider/model_id the creating host reported for the session (client reported, "
            "not verified); empty when none was reported"
        ),
    )


class CalibrationSessionRef(BaseModel):
    """A calibration session another record belongs to, read in the request's project."""

    calibration_session_id: str
    chip_id: str
    objective: str
    status: CalibrationSessionStatus


class ExecutionCalibrationSessionLink(CalibrationSessionRef):
    """The calibration session an execution belongs to, and the server record that says so.

    ``via`` names the record: ``pipeline_run`` when the execution is a step of a pipeline run
    recorded in the session (matched by project, chip, and flow run), ``agent_session`` when an
    action of an admitted agent session of the session dispatched it. Membership says what the
    work was for; it never says that an agent ran it.
    """

    via: Literal["pipeline_run", "agent_session"]
    pipeline_run_id: str | None = Field(
        default=None, description="The pipeline run, when via is pipeline_run"
    )
    agent_session_id: str | None = Field(
        default=None, description="The agent session, when via is agent_session"
    )


_CALIBRATION_SESSION_DESCRIPTION = (
    "The calibration session this execution belongs to, from QDash's own records: a pipeline "
    "run recorded in it, or an action of an agent session admitted to it. Null when no record "
    "relates it, or when records disagree on the session"
)
_REPORTED_ORIGIN_DESCRIPTION = (
    "How the caller that launched this execution's pipeline said it was started, such as an "
    "agent tool. Client reported, not verified by QDash; null when nothing was reported. The "
    "recorded user is still the one whose sign-in started it"
)


class ExecutionResponseSummary(BaseModel):
    """ExecutionResponseSummary is a Pydantic model that represents the summary of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        execution_id (str): The ID of the execution.
        status (str): The current status of the execution.
        start_at (datetime | None): The start time of the execution.
        end_at (datetime | None): The end time of the execution.
        elapsed_time (timedelta | None): The total elapsed time of the execution.
        user_id (str | None): Internal ID of the user who started the execution.
        username (str): Username snapshot of the user who started the execution.
        tags (list[str]): Tags associated with the execution.
        note (dict): Notes for the execution.

    """

    name: str
    execution_id: str
    status: str
    message: str = ""
    user_id: str | None = None
    username: str = ""
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    tags: list[str]
    note: dict[str, Any]
    agent_session: ExecutionAgentSessionLink | None = Field(
        default=None,
        description=(
            "Set only when an action of an agent session dispatched this execution; a tag "
            "alone never sets it"
        ),
    )
    calibration_session: ExecutionCalibrationSessionLink | None = Field(
        default=None, description=_CALIBRATION_SESSION_DESCRIPTION
    )
    reported_origin: ReportedLaunchOrigin | None = Field(
        default=None, description=_REPORTED_ORIGIN_DESCRIPTION
    )

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats."""
        return parse_elapsed_time(v)

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None


class PipelineStepProgress(BaseModel):
    """One planned step of a pipeline run and how far its execution got.

    Every step the run reaches, calibration or transform, has its own execution.
    """

    index: int = Field(description="1-based position in the pipeline spec")
    name: str
    step_id: str | None = Field(
        default=None, description="Plan-scoped step id; null for transforms and older runs"
    )
    key: str = Field(
        default="",
        description=(
            "Identifier of this step occurrence in the plan: the step_id of a calibration "
            "step; a transform's name, suffixed with its index when the name repeats"
        ),
    )
    type: str = ""
    kind: str = Field(default="calibration", description='"calibration" or "transform"')
    execution_id: str | None = Field(
        default=None, description="The step's own execution, once it has started"
    )
    status: str = Field(
        description=(
            'The execution status; "pending" before the step starts while the run may still '
            'reach it; "skipped" when the run ended without reaching it; "not_recorded" for a '
            "transform of a run recorded before transform steps had executions"
        )
    )
    transform: TransformStepRecord | None = Field(
        default=None,
        description=(
            "A transform step's recorded outcome: candidates kept and excluded with reasons, "
            "or the CR groups planned; null for calibration steps and unfinished transforms"
        ),
    )
    task_total: int = 0
    task_finished: int = 0
    task_failed: int = 0
    figure_paths: list[str] = Field(
        default_factory=list, description="Figures of the step's finished tasks, in task order"
    )


class PipelineProgress(BaseModel):
    """A pipeline run as a whole: one execution per step it reached, same flow run.

    ``status`` is the whole run's: running while any step runs or the run holds
    the project lock between steps, otherwise the outcome of the last step.
    """

    name: str
    flow_run_id: str
    root_execution_id: str = Field(
        description="The first step's execution, as returned at dispatch"
    )
    status: str
    steps: list[PipelineStepProgress]


class ExecutionResponseDetail(BaseModel):
    """ExecutionResponseDetail is a Pydantic model that represents the detail of an execution response.

    Attributes
    ----------
        name (str): The name of the execution.
        status (str): The current status of the execution.
        start_at (datetime | None): The start time of the execution.
        end_at (datetime | None): The end time of the execution.
        elapsed_time (timedelta | None): The total elapsed time of the execution.
        user_id (str | None): Internal ID of the user who started the execution.
        username (str): Username snapshot of the user who started the execution.
        task (list[Task]): List of tasks in the execution.
        note (dict): Notes for the execution.
        tags (list[str]): Tags associated with the execution.
        chip_id (str): The chip ID for the execution.

    """

    name: str
    status: str
    message: str = ""
    flow_name: str = ""
    user_id: str | None = None
    username: str = ""
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_time: timedelta | None = None
    task: list[Task]
    note: dict[str, Any]
    tags: list[str] = []
    chip_id: str = ""
    pipeline: PipelineProgress | None = Field(
        default=None,
        description="Set when this execution belongs to a pipeline run; covers every step of it",
    )
    agent_session: ExecutionAgentSessionLink | None = Field(
        default=None,
        description=(
            "The agent session whose action dispatched this execution, or the session only "
            "its tag names (linked false); null for an execution outside agent sessions"
        ),
    )
    calibration_session: ExecutionCalibrationSessionLink | None = Field(
        default=None, description=_CALIBRATION_SESSION_DESCRIPTION
    )
    reported_origin: ReportedLaunchOrigin | None = Field(
        default=None, description=_REPORTED_ORIGIN_DESCRIPTION
    )

    @field_validator("elapsed_time", mode="before")
    @classmethod
    def _parse_elapsed_time(cls, v: Any) -> timedelta | None:
        """Parse elapsed_time from various formats."""
        return parse_elapsed_time(v)

    @field_serializer("elapsed_time")
    @classmethod
    def _serialize_elapsed_time(cls, v: timedelta | None) -> str | None:
        """Serialize elapsed_time to H:MM:SS format."""
        return format_elapsed_time(v) if v else None


class CancelExecutionResponse(BaseModel):
    """Response model for cancelling an execution."""

    execution_id: str
    status: str
    message: str


ExecutionActivityGranularity = Literal["day", "6h"]
"""Bucket length of the activity counts: a calendar day, or a quarter of one."""


class ExecutionActivityDay(BaseModel):
    """Executions started in one bucket (a calendar day or a 6-hour slot), counted by status."""

    date: str = Field(
        ...,
        description=(
            "Calendar day in the requested time zone, YYYY-MM-DD; for a 6-hour bucket, "
            "the day the bucket starts on"
        ),
    )
    start: datetime = Field(
        ...,
        description=(
            "Start of the bucket, inclusive, in UTC; local midnight, or local 00:00, 06:00, "
            "12:00, or 18:00 for a 6-hour bucket, in the requested time zone"
        ),
    )
    end: datetime = Field(
        ...,
        description=(
            "End of the bucket, exclusive, in UTC; the next "
            "bucket's start. Boundaries are local wall-clock hours, so a bucket that spans a "
            "DST change is an hour shorter or longer"
        ),
    )
    completed: int = 0
    failed: int = 0
    running: int = Field(0, description="Executions still in progress (running, cancelling)")
    scheduled: int = Field(0, description="Executions not started yet (scheduled, pending)")
    cancelled: int = 0
    other: int = Field(0, description="Any status not covered by the named buckets")
    total: int = 0


class ExecutionActivityResponse(BaseModel):
    """Execution counts for a chip, or a whole project, over a trailing window of days."""

    chip_id: str | None = Field(
        ..., description="Chip the counts are for, or null when every chip in the project counts"
    )
    days: int = Field(..., description="Length of the window in calendar days")
    timezone: str = Field(..., description="IANA time zone the days are bucketed in")
    granularity: ExecutionActivityGranularity = Field(
        ...,
        description=(
            "Bucket length: `day` for one bucket per calendar day, `6h` for four buckets "
            "per day starting at local 00:00, 06:00, 12:00, and 18:00"
        ),
    )
    since: str = Field(..., description="Day the first bucket starts on, YYYY-MM-DD")
    until: str = Field(..., description="Day the last bucket starts on (today), YYYY-MM-DD")
    buckets: list[ExecutionActivityDay] = Field(
        ...,
        description=(
            "One entry per bucket, oldest first, including empty buckets. Daily: one per "
            "calendar day ending today. 6-hour: `days` x 4 slots ending with the slot that "
            "contains the current time, so no bucket lies entirely in the future"
        ),
    )


class ListExecutionsResponse(BaseModel):
    """Response model for listing executions.

    Wraps list of executions for API consistency and future extensibility (e.g., pagination).
    """

    executions: list[ExecutionResponseSummary]
    total: int | None = None
    skip: int | None = None
    limit: int | None = None
