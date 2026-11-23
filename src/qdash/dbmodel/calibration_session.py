"""Persistence models for calibration sessions and the pipeline runs requested in them."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Bunnet resolves this runtime annotation
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import (
    CalibrationChildReservation,
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
