"""Calibration sessions: one calibration objective and the runs that work toward it.

A calibration session groups the runs and agent sessions started for one objective on one
chip. A run is one launch of a saved workflow, a calibration pipeline, a single task, or an
agent action; every step execution of the run carries the session and run IDs in its note.
A session is a record of purpose, not an authority: it grants no operation, holds no hardware,
and stops nothing. Each child keeps its own authority (an agent session its policy, gates,
expiry, and pause; a run the approval of its exact request and the execution lock), and each
relation is an explicit server record written when the child was started. Nothing is grouped
by chip, time, tag, or chat.

A run is its own durable record (``qdash.datamodel.run``); its session is an association, not
part of the run's identity. A run or agent session started without a session ID gets a session
of its own (``origin`` ``automatic``), created before the launch; one started with a session
ID joins that session or is refused.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - pydantic resolves this runtime annotation
from enum import StrEnum

from pydantic import BaseModel

# Run vocabulary, defined with the run; re-exported here, where it was first defined.
from qdash.datamodel.run import (
    RUN_CONTEXT_KEY,
    CalibrationPipelineRunStatus,
    CalibrationRunKind,
    CalibrationRunTrigger,
    RunIdentity,
)

# Earlier names of the run identity and its context key.
CalibrationRunIdentity = RunIdentity
CALIBRATION_RUN_CONTEXT_KEY = RUN_CONTEXT_KEY

__all__ = [
    "CALIBRATION_RUN_CONTEXT_KEY",
    "CalibrationAdmission",
    "CalibrationChildKind",
    "CalibrationChildReservation",
    "CalibrationDecisionOutcome",
    "CalibrationExperimentStage",
    "CalibrationPipelineRunStatus",
    "CalibrationRunIdentity",
    "CalibrationRunKind",
    "CalibrationRunTrigger",
    "CalibrationSessionCloseOrigin",
    "CalibrationSessionOrigin",
    "CalibrationSessionStatus",
]


class CalibrationSessionStatus(StrEnum):
    """Whether a calibration session accepts new runs.

    ``closed`` says that work on the objective has ended: a person's statement, or, for an
    automatic session, QDash's record that everything started in it ended (see
    ``CalibrationSessionCloseOrigin``). It says nothing about whether the objective was met or
    how the runs ended, and is refused while a child still runs or waits.
    """

    OPEN = "open"
    CLOSED = "closed"


class CalibrationSessionOrigin(StrEnum):
    """How a calibration session came to exist.

    ``manual``: a person or agent created it for an objective (every session recorded before
    automatic sessions existed). ``automatic``: QDash created it for a run started without a
    session ID; it is an ordinary session that a later run may name to add to it.
    """

    MANUAL = "manual"
    AUTOMATIC = "automatic"


class CalibrationSessionCloseOrigin(StrEnum):
    """Who closed a calibration session.

    ``manual``: the person who created it closed it (every session closed before this was
    recorded). ``automatic``: QDash closed an automatic session once every run and agent
    session in it had ended and nothing was being started, dispatched, or settled in it. An
    automatic close only stops new runs from joining; it cancels nothing and judges nothing.
    """

    MANUAL = "manual"
    AUTOMATIC = "automatic"


class CalibrationChildKind(StrEnum):
    """What a child of a calibration session is."""

    PIPELINE_RUN = "pipeline_run"
    AGENT_SESSION = "agent_session"


class CalibrationAdmission(StrEnum):
    """Whether an agent session created in a calibration session may operate.

    An agent session created with a calibration session ID is written ``pending`` and can do
    nothing (no action, measurement, commit, apply, or pause) until its reservation in the
    calibration session is finalized. Finalizing removes the reservation and records its ID in
    ``CalibrationSessionDocument.admitted_reservation_ids`` in one update, so the outcome is
    durable proof in the parent:

    ``admitted``: the reservation was finalized; the session operates under its own policy.
    ``rejected``: the reservation was cleared without being finalized (the calibration session
    was closed first). The session is cancelled and never operates.

    A session created alone, or before admission existed, has no admission and keeps the
    behavior it always had.
    """

    PENDING = "pending"
    ADMITTED = "admitted"
    REJECTED = "rejected"


class CalibrationChildReservation(BaseModel):
    """A child counted in a calibration session before its own record is written.

    The reservation is pushed into the session by the same conditional update that checks the
    session is open, with the ID the child will have. The request that made it removes it
    (``finalize``) once the child's record exists, and only then may a pipeline run be
    launched. Closing the session clears every reservation it accepts; a request whose
    reservation was cleared undoes its child instead of starting it.
    """

    reservation_id: str
    kind: CalibrationChildKind
    child_id: str
    reserved_by: str
    reserved_at: datetime


class CalibrationExperimentStage(StrEnum):
    """Where one experiment stands in an optimization search.

    ``baseline``: the incumbent's evidence the search starts from.
    ``screening``: a candidate condition measured to decide whether it is worth confirming.
    ``confirmation``: a whole-arm rerun of a candidate or the incumbent, used for the final
    comparison. Only confirmation evidence may back a recommendation of a new candidate.
    """

    BASELINE = "baseline"
    SCREENING = "screening"
    CONFIRMATION = "confirmation"


class CalibrationDecisionOutcome(StrEnum):
    """What a final decision recommends; a statement of the person or agent recording it.

    ``recommend_candidate``: a candidate other than the baseline, backed by its confirmation
    experiments. ``keep_baseline``: the baseline candidate stays the recommendation.
    ``inconclusive``: the evidence supports no recommendation.
    """

    RECOMMEND_CANDIDATE = "recommend_candidate"
    KEEP_BASELINE = "keep_baseline"
    INCONCLUSIVE = "inconclusive"
