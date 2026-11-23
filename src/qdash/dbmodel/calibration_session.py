"""Persistence models for calibration sessions and the pipeline runs requested in them."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Bunnet resolves this runtime annotation
from typing import Any, ClassVar

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (  # noqa: TC001 - Bunnet field types
    AgentDecisionAssessment,
    AgentDecisionNextAction,
    AgentModelIdentity,
)
from qdash.datamodel.calibration_session import (
    CalibrationChildReservation,
    CalibrationDecisionOutcome,
    CalibrationExperimentStage,
    CalibrationPipelineRunStatus,
    CalibrationSessionStatus,
)
from qdash.datamodel.launch_origin import ReportedLaunchOrigin  # noqa: TC001 - Bunnet field


class CalibrationSessionDocument(Document):
    """One calibration objective on one chip.

    Agent sessions name it in ``AgentSessionDocument.calibration_session_id``; pipeline runs
    are ``CalibrationPipelineRunDocument`` records. Neither is copied here, so the session
    record changes only when it is closed.
    """

    calibration_session_id: str
    project_id: str
    chip_id: str
    objective: str
    # The signed-in user who created it, from the request's authentication.
    created_by: str
    status: CalibrationSessionStatus = CalibrationSessionStatus.OPEN
    # Raised, on the condition that the session is open, before every run or agent session is
    # started in it. Closing compares it with the value its check of the children read, so a
    # child started meanwhile makes the close fail instead of being hidden by it.
    child_count: int = 0
    # Children counted by the update above whose request has not finished writing them: added
    # with the count, removed by that request once the child's record exists. A close is
    # refused while a recent one is pending, and clears the rest in its own update.
    pending_children: list[CalibrationChildReservation] = Field(default_factory=list)
    # Reservations of agent sessions whose start was finalized: pushed by the same update that
    # removes the reservation, so a reservation is either pending, finalized (listed here), or
    # cleared by a close, and an agent session's admission is read from this record.
    admitted_reservation_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    closed_at: datetime | None = None
    closed_by: str | None = None
    closing_note: str = ""
    # Runs whose dispatch outcome was unknown when the session was closed; the person who
    # closed it stated that they checked them.
    closed_with_unknown_runs: list[str] = Field(default_factory=list)
    # Agent sessions whose start was reserved long ago and never recorded when the session was
    # closed; the person who closed it acknowledged them. One recorded later stays ``pending``
    # admission, is rejected, and never operates.
    closed_with_unknown_starts: list[CalibrationChildReservation] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "calibration_sessions"
        indexes: ClassVar = [
            IndexModel([("calibration_session_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("created_at", DESCENDING),
                ]
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("created_by", ASCENDING),
                    ("created_at", DESCENDING),
                ]
            ),
        ]


class CalibrationPipelineRunDocument(Document):
    """One pipeline run requested in a calibration session, recorded before it is launched.

    The record is inserted against its unique ``(project_id, calibration_session_id,
    idempotency_key)`` before the flow run is created, so a retry finds it instead of
    launching again. ``dispatch_token`` names the attempt that holds the launch; only that
    attempt settles it. Once dispatched, the pipeline's step executions are the executions of
    the project and chip whose ``note.flow_run_id`` is ``flow_run_id``.
    """

    run_id: str
    project_id: str
    calibration_session_id: str
    chip_id: str
    idempotency_key: str
    request_hash: str
    requested_by: str
    # How the caller said it started the run (client reported, never verified); None when it
    # reported nothing. ``requested_by`` stays the user the request authenticated.
    reported_origin: ReportedLaunchOrigin | None = None
    status: CalibrationPipelineRunStatus = CalibrationPipelineRunStatus.DISPATCHING
    dispatch_token: str
    # The calibration session reservation of the attempt that holds ``dispatch_token``. The
    # attempt launches only after removing that reservation, so a run still ``dispatching``
    # whose reservation is pending or was cleared by a close was never launched.
    reservation_id: str | None = None
    attempts: int = 1
    pipeline_name: str = ""
    backend_name: str = ""
    flow_run_id: str | None = None
    # The execution QDash pre-created for the first step; None when pre-creation failed.
    execution_id: str | None = None
    # The dispatch response, returned unchanged to a retry of the same request.
    response: dict[str, Any] | None = None
    error: str = ""
    # The normalized spec QDash validated for the attempt that holds the launch: the exact
    # request, so the audit can compare requested and executed run parameters. None for runs
    # recorded before it was stored.
    spec: dict[str, Any] | None = None
    # The decision of the session this run carries out, named by the request; None when the
    # request named none (every run recorded before decisions existed).
    decision_id: str | None = None
    requested_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "calibration_pipeline_runs"
        indexes: ClassVar = [
            IndexModel([("run_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("calibration_session_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("calibration_session_id", ASCENDING),
                    ("requested_at", ASCENDING),
                ]
            ),
            # The Execution list finds the run a step execution belongs to by its flow run.
            IndexModel([("project_id", ASCENDING), ("flow_run_id", ASCENDING)]),
        ]


class RequestedParameterChange(BaseModel):
    """One run parameter a decision asks a task to use, as the recorder stated it."""

    task_name: str
    call_id: str | None = None
    parameter: str
    value: bool | int | float | str | None = None
    previous: bool | int | float | str | None = None


class CalibrationExperimentPlan(BaseModel):
    """The experiment a decision proposes: candidate identity, stage, target, and changes."""

    candidate_id: str
    stage: CalibrationExperimentStage
    target: str
    requested_changes: list[RequestedParameterChange] = Field(default_factory=list)


class CalibrationConclusion(BaseModel):
    """What a concluding decision recommends; a statement of its recorder."""

    outcome: CalibrationDecisionOutcome
    recommended_candidate_id: str | None = None


class CalibrationDecisionDocument(Document):
    """One decision in a calibration session's audit, shaped like an agent session decision.

    The same audit semantics as ``AgentDecisionDocument``: the recorder's assessment,
    interpretation, and chosen next step, with references to evidence that QDash checked
    belongs to the session and a frozen ``evidence_snapshot`` of what its records said then.
    Evidence here is the session's own: its pipeline runs, task results on its chip, and its
    earlier decisions. ``experiment`` states the run a decision proposes before it is
    dispatched; a pipeline run started with ``decision_id`` records which decision it carries
    out. ``conclusion`` states a final recommendation. Records are append-only; a correction
    supersedes an earlier decision. A decision grants nothing and changes no session state.
    """

    decision_id: str
    project_id: str
    calibration_session_id: str
    chip_id: str
    idempotency_key: str
    request_hash: str
    recorded_by: str
    recorded_at: datetime = Field(default_factory=now)
    session_status_at_record: str
    assessment: AgentDecisionAssessment | None = None
    interpretation: str
    next_action: AgentDecisionNextAction
    next_detail: str = ""
    evidence_run_ids: list[str] = Field(default_factory=list)
    evidence_task_ids: list[str] = Field(default_factory=list)
    evidence_decision_ids: list[str] = Field(default_factory=list)
    supersedes_decision_id: str | None = None
    experiment: CalibrationExperimentPlan | None = None
    conclusion: CalibrationConclusion | None = None
    # What QDash's records said about the cited evidence when the decision was recorded.
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    # The model the client host reported; client reported, not verified.
    model: AgentModelIdentity | None = None
    # Position in the session's decision quota; unique per session, so a quota race is decided
    # by the insert itself.
    quota_slot: int

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """MongoDB collection settings."""

        name = "calibration_decisions"
        indexes: ClassVar = [
            IndexModel([("decision_id", ASCENDING)], unique=True),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("calibration_session_id", ASCENDING),
                    ("idempotency_key", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("calibration_session_id", ASCENDING),
                    ("recorded_at", ASCENDING),
                ]
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("calibration_session_id", ASCENDING),
                    ("quota_slot", ASCENDING),
                ],
                unique=True,
            ),
        ]
