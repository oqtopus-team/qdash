"""Calibration sessions: one calibration objective and the runs that work toward it.

A calibration session groups the pipeline runs and agent sessions started for one objective on
one chip. It is a record of purpose, not an authority: it grants no operation, holds no
hardware, and stops nothing. Each child keeps its own authority (an agent session its policy,
gates, expiry, and pause; a pipeline run the approval of its exact request and the execution
lock), and each relation is an explicit server record written when the child was started with
the session's ID. Nothing is grouped by chip, time, tag, or chat.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - pydantic resolves this runtime annotation
from enum import StrEnum

from pydantic import BaseModel


class CalibrationSessionStatus(StrEnum):
    """Whether a calibration session accepts new runs.

    ``closed`` is a person's statement that work on the objective has ended. It says nothing
    about whether the objective was met and is refused while a child still runs or waits.
    """

    OPEN = "open"
    CLOSED = "closed"


class CalibrationPipelineRunStatus(StrEnum):
    """Dispatch state of one pipeline run requested in a calibration session.

    ``dispatching``: the request was recorded and its launch has not reported back.
    ``dispatched``: QDash created the pipeline's flow run; its executions carry its
    ``flow_run_id``.
    ``rejected``: QDash refused the launch before any flow run was created (the hardware was
    busy or the worker deployment was missing); a retry with the same key may launch it.
    ``unknown``: the launch failed in a way that may have created a flow run anyway, or it
    stayed ``dispatching`` past the time a launch takes. A retry with the same key never
    launches it again.
    """

    DISPATCHING = "dispatching"
    DISPATCHED = "dispatched"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


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
