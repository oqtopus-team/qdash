"""API schemas for calibration sessions: one objective, its runs and agent sessions."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - pydantic resolves this runtime annotation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from qdash.api.schemas.agent_session import AgentAuditEvent  # noqa: TC001 - pydantic field
from qdash.api.schemas.execution import (  # noqa: TC001 - pydantic field types
    ExecutionResponseSummary,
    PipelineProgress,
)
from qdash.datamodel.agent_session import (
    AgentAutonomy,
    AgentDecisionAssessment,
    AgentDecisionNextAction,
    AgentModelIdentity,
    AgentSessionStatus,
)
from qdash.datamodel.calibration_session import (
    CalibrationAdmission,
    CalibrationChildReservation,
    CalibrationDecisionOutcome,
    CalibrationExperimentStage,
    CalibrationPipelineRunStatus,
    CalibrationRunKind,
    CalibrationRunTrigger,
    CalibrationSessionOrigin,
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
    origin: CalibrationSessionOrigin = Field(
        default=CalibrationSessionOrigin.MANUAL,
        description=(
            "manual when a person or agent created it for an objective; automatic when QDash "
            "created it for a run started without a session ID (a later run may name it)"
        ),
    )
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
    """One run requested in a calibration session, with its step executions."""

    run_id: str
    calibration_session_id: str
    chip_id: str
    run_kind: CalibrationRunKind = Field(
        default=CalibrationRunKind.PIPELINE,
        description="What the run launched: a pipeline, a saved workflow, a task, or an agent action",
    )
    trigger: CalibrationRunTrigger = Field(
        default=CalibrationRunTrigger.API,
        description=(
            "api when a signed-in request recorded it before launch; schedule or worker when "
            "the worker recorded a flow run QDash had not launched (a schedule) as it started"
        ),
    )
    run_name: str = Field(
        default="", description="The workflow or pipeline name, or the task the run launched"
    )
    agent_session_id: str | None = Field(
        default=None, description="For an agent action's run, the agent session that ran it"
    )
    action_id: str | None = Field(
        default=None, description="For an agent action's run, the action that dispatched it"
    )
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
        description=(
            "Every step execution of the run on the chip, oldest first: those the worker "
            "stamped with the run, or, for older runs, those of its flow run"
        ),
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


# ---------------------------------------------------------------- decisions and audit

RECORD_ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"
TARGET_PATTERN = r"^[A-Za-z0-9_]{1,32}(-[A-Za-z0-9_]{1,32})?$"
ParameterValue = bool | int | float | str | None
_REFERENCE = Annotated[str, Field(min_length=1, max_length=200)]
# Next actions after which a decision may propose an experiment, and conclude.
PROPOSING_NEXT_ACTIONS = frozenset(
    {
        AgentDecisionNextAction.NEXT_TASK,
        AgentDecisionNextAction.REPEAT,
        AgentDecisionNextAction.ADJUST_AND_RETRY,
    }
)
CONCLUDING_NEXT_ACTIONS = frozenset(
    {AgentDecisionNextAction.COMPLETE, AgentDecisionNextAction.STOP}
)


class RequestedParameterChangeModel(BaseModel):
    """One run parameter a decision asks a task to use, as the recorder states it."""

    task_name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_]+$")
    call_id: str | None = Field(
        default=None,
        max_length=100,
        description="The task call the change is for, when a step calls the task more than once",
    )
    parameter: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.]+$")
    value: ParameterValue = None
    previous: ParameterValue = Field(
        default=None, description="The value before the change, when the recorder knows it"
    )


class CalibrationExperimentPlanModel(BaseModel):
    """The experiment a decision proposes before its run is dispatched."""

    candidate_id: str = Field(
        pattern=RECORD_ID_PATTERN,
        description="The recorder's name for the condition, such as incumbent or c03",
    )
    stage: CalibrationExperimentStage
    target: str = Field(
        pattern=TARGET_PATTERN, description="The qubit (0) or directed coupling (0-1) measured"
    )
    requested_changes: list[RequestedParameterChangeModel] = Field(
        default_factory=list, max_length=20
    )


class CalibrationConclusionModel(BaseModel):
    """A final recommendation; a statement of its recorder, never implied by closing."""

    outcome: CalibrationDecisionOutcome
    recommended_candidate_id: str | None = Field(default=None, pattern=RECORD_ID_PATTERN)

    @model_validator(mode="after")
    def candidate_matches_outcome(self) -> CalibrationConclusionModel:
        """recommend_candidate and keep_baseline name a candidate; inconclusive names none."""
        names = self.outcome != CalibrationDecisionOutcome.INCONCLUSIVE
        if names != (self.recommended_candidate_id is not None):
            raise ValueError(
                "recommended_candidate_id is given exactly for recommend_candidate and "
                "keep_baseline"
            )
        return self


class RecordCalibrationDecisionRequest(BaseModel):
    """Record a decision in a calibration session's audit, as an agent session decision is.

    The text fields are the recorder's statements, recorded as given. QDash checks that every
    cited pipeline run and decision belongs to the session and every cited task result is on
    its chip (and on the experiment's target), and freezes what its records say about them.
    Record ``experiment`` before dispatching the run it proposes, then start the run with this
    decision's ID. ``conclusion`` needs next_action complete or stop.
    """

    idempotency_key: str = Field(min_length=1, max_length=128)
    assessment: AgentDecisionAssessment | None = Field(
        default=None, description="How the recorder judged the evidence; omitted when not stated"
    )
    interpretation: str = Field(
        min_length=1,
        max_length=2000,
        description="Concise reasoning for the decision, citing the evidence",
    )
    next_action: AgentDecisionNextAction
    next_detail: str = Field(default="", max_length=500)
    evidence_run_ids: list[_REFERENCE] = Field(
        default_factory=list, max_length=20, description="Pipeline runs of this session"
    )
    evidence_task_ids: list[_REFERENCE] = Field(
        default_factory=list, max_length=50, description="Task results on the session's chip"
    )
    evidence_decision_ids: list[_REFERENCE] = Field(
        default_factory=list, max_length=50, description="Earlier decisions of this session"
    )
    supersedes_decision_id: str | None = Field(default=None, min_length=1, max_length=200)
    experiment: CalibrationExperimentPlanModel | None = None
    conclusion: CalibrationConclusionModel | None = None
    model: AgentModelIdentity | None = Field(
        default=None,
        description=(
            "The model the client host reports for this record; client reported, not verified"
        ),
    )

    @model_validator(mode="after")
    def blocks_match_next_action(self) -> RecordCalibrationDecisionRequest:
        """An experiment is proposed by a next step; a conclusion ends the search."""
        if self.experiment is not None and self.next_action not in PROPOSING_NEXT_ACTIONS:
            raise ValueError("experiment needs next_action next_task, repeat, or adjust_and_retry")
        if self.conclusion is not None:
            if self.next_action not in CONCLUDING_NEXT_ACTIONS:
                raise ValueError("conclusion needs next_action complete or stop")
            if not (self.evidence_run_ids or self.evidence_decision_ids):
                raise ValueError("a conclusion cites evidence_run_ids or evidence_decision_ids")
        return self


class CalibrationDecisionResponse(BaseModel):
    """One recorded decision with QDash's frozen reading of its evidence."""

    decision_id: str
    calibration_session_id: str
    project_id: str
    chip_id: str
    idempotency_key: str
    recorded_by: str
    recorded_at: datetime
    session_status_at_record: str
    assessment: AgentDecisionAssessment | None = None
    interpretation: str
    next_action: AgentDecisionNextAction
    next_detail: str = ""
    evidence_run_ids: list[str] = Field(default_factory=list)
    evidence_task_ids: list[str] = Field(default_factory=list)
    evidence_decision_ids: list[str] = Field(default_factory=list)
    supersedes_decision_id: str | None = None
    experiment: CalibrationExperimentPlanModel | None = None
    conclusion: CalibrationConclusionModel | None = None
    evidence_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="What QDash's records said about the cited evidence when it was recorded",
    )
    model: AgentModelIdentity | None = None
    carried_out_by_run_ids: list[str] = Field(
        default_factory=list,
        description="Pipeline runs that named this decision when they were started",
    )
    superseded_by_decision_id: str | None = None


class ListCalibrationDecisionsResponse(BaseModel):
    """Decisions of one calibration session, oldest first."""

    items: list[CalibrationDecisionResponse]
    total: int


class CalibrationMeasuredValue(BaseModel):
    """One output parameter of a task result, read from QDash's task result history."""

    value: float
    error: float | None = Field(default=None, description="The task's reported error, if any")
    unit: str = ""
    task_id: str
    task_name: str
    execution_id: str


class CalibrationMeasuredTask(BaseModel):
    """A task result on the experiment's target, with its actual timing."""

    task_id: str
    name: str
    status: str
    execution_id: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    elapsed_seconds: float | None = None


EvidenceStatus = Literal["complete", "partial", "running", "failed", "unavailable", "not_run"]


class CalibrationExperimentMeasurement(BaseModel):
    """What QDash's task results say an experiment measured; never the recorder's statement.

    ``evidence_status``: ``complete`` when every task on the target completed, ``running``
    while an execution or task still runs, ``failed`` when none completed and one failed,
    ``partial`` when some completed and others failed or were cancelled, ``unavailable`` when
    no task result on the target was found, ``not_run`` when no run carries the decision out
    (never dispatched, declined, or refused before it started). It never says whether the
    experiment succeeded scientifically.
    """

    evidence_status: EvidenceStatus
    pipeline_dispatch_status: CalibrationPipelineRunStatus | None = None
    execution_ids: list[str] = Field(default_factory=list)
    tasks: list[CalibrationMeasuredTask] = Field(default_factory=list)
    gate_time_ns: CalibrationMeasuredValue | None = Field(
        default=None, description="zx90_gate_time of the latest completed task that published it"
    )
    cr_duration_ns: CalibrationMeasuredValue | None = None
    cr_amplitude: CalibrationMeasuredValue | None = None
    gate_fidelity: CalibrationMeasuredValue | None = Field(
        default=None, description="zx90_gate_fidelity, with the benchmark's error"
    )
    task_seconds: float | None = Field(
        default=None, description="Sum of the target's task durations; null when none ended"
    )
    execution_seconds: float | None = Field(
        default=None,
        description="From the first execution start to the last end; null until all ended",
    )


class CalibrationParameterCheck(BaseModel):
    """One requested change, compared with the exact request and with what the task used.

    ``requested`` is the decision's statement; ``in_spec`` is the run's stored spec (server
    record); ``executed`` is the task result's run parameter (server record). ``consistent`` is
    null when either record is missing.
    """

    task_name: str
    call_id: str | None = None
    parameter: str
    requested: ParameterValue = None
    in_spec: ParameterValue = None
    executed: ParameterValue = None
    consistent: bool | None = None
    missing: list[str] = Field(default_factory=list)


class CalibrationExperimentRow(BaseModel):
    """One experiment of the search: a proposing decision and one run that carried it out.

    A decision carried out by several runs gives a row per run; one carried out by none gives a
    row without a run. Built from the audit's records; nothing here is stored.
    """

    sequence: int = Field(description="1-based order among the rows")
    decision_id: str
    stage: CalibrationExperimentStage
    candidate_id: str
    target: str
    requested_changes: list[RequestedParameterChangeModel] = Field(default_factory=list)
    rationale: str = Field(description="The decision's interpretation; recorder's statement")
    model: AgentModelIdentity | None = None
    recorded_at: datetime
    pipeline_run_id: str | None = None
    parameter_checks: list[CalibrationParameterCheck] = Field(default_factory=list)
    measured: CalibrationExperimentMeasurement


RequestedRunExecutionOutcome = Literal[
    "refused", "unknown", "no_execution", "running", "failed", "partial", "completed"
]

HARDWARE_WRITE_NOT_RECORDED = (
    "an authoritative record of what this run wrote to the hardware or calibration store; "
    "request order and execution outcome do not prove which run wrote last"
)


class CalibrationLatestRequestedRun(BaseModel):
    """The session's most recently requested pipeline run and its recorded execution outcome.

    "Latest" is the order QDash recorded the requests in (``requested_at``), not the order runs
    finished or wrote: a run requested earlier may complete later. QDash keeps no authoritative
    record of hardware writes, so this never states the current or last written hardware state.

    ``execution_outcome``, from QDash's dispatch and execution records only: ``refused``: QDash
    refused the launch and created no flow run. ``unknown``: the launch is still being reported
    or its outcome is unknown. ``no_execution``: the flow run was created and QDash holds no
    execution record for it. ``running``: an execution is still open. ``failed``: every
    execution ended and none completed. ``partial``: some executions completed and others
    failed or were cancelled. ``completed``: every execution completed. Runs outside the
    session are not considered.
    """

    pipeline_run_id: str
    requested_at: datetime
    dispatch_status: CalibrationPipelineRunStatus
    execution_outcome: RequestedRunExecutionOutcome
    decision_id: str | None = Field(
        default=None, description="The decision the request named; never inferred"
    )
    candidate_id: str | None = Field(
        default=None,
        description="The candidate of the decision the run carries out; null when it names none",
    )
    execution_ids: list[str] = Field(default_factory=list)
    finished_at: datetime | None = Field(
        default=None, description="When the last of its executions ended; null while any is open"
    )
    candidate_is_recommended: bool | None = Field(
        default=None,
        description=(
            "Whether the run's requested candidate is the recommended candidate, comparing the "
            "two records only; null when either is unknown. It says nothing about the hardware"
        ),
    )
    missing: list[str] = Field(
        default_factory=lambda: [HARDWARE_WRITE_NOT_RECORDED],
        description="Facts QDash does not record and this view therefore cannot state",
    )


class CalibrationAuditSessionHeader(BaseModel):
    """Who and what a calibration session's audit belongs to."""

    calibration_session_id: str
    project_id: str
    chip_id: str
    objective: str
    created_by: str
    created_at: datetime
    status: CalibrationSessionStatus
    pipeline_run_total: int
    agent_session_total: int
    decision_total: int


class CalibrationSessionAuditResponse(BaseModel):
    """A page of one snapshot of a calibration session's audit, or all of it.

    The events have the same schema and semantics as an agent session's audit, and an admitted
    agent session's events appear inside it with ``agent_session_id`` set. A snapshot is two
    matching projected reads, not an atomic database view.
    """

    schema_version: Literal["qdash.calibration-session-audit.v1"] = (
        "qdash.calibration-session-audit.v1"
    )
    generated_at: datetime
    snapshot_id: str
    calibration_session: CalibrationAuditSessionHeader
    events: list[AgentAuditEvent]
    total_events: int
    next_cursor: str | None = None
    complete: bool
    notes: list[str]


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
    experiments: list[CalibrationExperimentRow] = Field(
        default_factory=list,
        description=(
            "Experiments of the search, oldest first, from decisions that proposed one and the "
            "runs that named them (latest 200 decisions)"
        ),
    )
    decisions: list[CalibrationDecisionResponse] = Field(
        default_factory=list, description="The most recent decisions (at most 200), oldest first"
    )
    decision_total: int = Field(default=0, description="Every decision recorded in it")
    recommendation: CalibrationDecisionResponse | None = Field(
        default=None,
        description=(
            "The latest decision with a conclusion that no later decision supersedes; null "
            "when none was recorded. Closing records none"
        ),
    )
    latest_requested_run: CalibrationLatestRequestedRun | None = Field(
        default=None,
        description=(
            "The most recently requested pipeline run and its recorded execution outcome; null "
            "without a run. Not the current or last written hardware state"
        ),
    )
