"""Calibration run identity shared by the API and the workflow worker.

Every run QDash starts belongs to one calibration session and is one
``CalibrationPipelineRunDocument``, and every step execution of the run carries both IDs in
its note (``calibration_session_id`` and ``calibration_run_id``). The API records the run
before it launches the flow run and hands its identity, with the dispatch token of the launch
attempt, to the worker in the flow-run context (``CALIBRATION_RUN_CONTEXT_KEY``). The worker
binds its flow run to the run only by presenting that token, once: a flow run that only names
a run's IDs claims nothing. A flow run the API did not launch (a cron or one-time
schedule, or a run started in Prefect directly) carries none; the worker records it when the
flow starts, with IDs derived from the flow run, so a Prefect retry of the same flow run finds
the same records instead of adding others.

Mongo runs standalone, so each write here is one insert or one conditional update of one
document, and every insert is keyed by a unique ID so that repeating it changes nothing.
Nothing is inferred from names, tags, chips, or times.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from pymongo.errors import DuplicateKeyError

from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import (
    CalibrationPipelineRunStatus,
    CalibrationRunIdentity,
    CalibrationRunKind,
    CalibrationRunTrigger,
    CalibrationSessionOrigin,
)
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)

# Prefect flow names of the system deployments, and the kind of run each launches. Any other
# flow is a saved workflow.
SYSTEM_FLOW_KINDS = {
    "calibration-pipeline": CalibrationRunKind.PIPELINE,
    "single-task-executor": CalibrationRunKind.TASK,
}
# Execution note keys the worker stamps on every step execution of a run.
NOTE_SESSION_KEY = "calibration_session_id"
NOTE_RUN_KEY = "calibration_run_id"
# The value of the context key for a run QDash deliberately leaves without a session: an
# action of an agent session created before automatic sessions existed, whose executions stay
# in that agent session alone.
UNGROUPED_MARKER = "ungrouped"


class CalibrationRunMismatch(RuntimeError):
    """A recorded run or session does not belong to the project, chip, or user at hand."""


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


def automatic_session_id_for_key(project_id: str, username: str, idempotency_key: str) -> str:
    """The automatic session of a request's idempotency key: the same on every retry."""
    return f"cs-auto-{_digest(project_id, username, idempotency_key)}"


def automatic_session_id_for_flow_run(flow_run_id: str) -> str:
    """The automatic session the worker records for a flow run QDash did not launch."""
    return f"cs-flow-{flow_run_id}"


def run_id_for_flow_run(flow_run_id: str) -> str:
    """The run the worker records for a flow run QDash did not launch."""
    return f"cpr-flow-{flow_run_id}"


def run_kind_of_flow(flow_name: str | None) -> CalibrationRunKind:
    """The kind of run a Prefect flow launches, from its flow name."""
    return SYSTEM_FLOW_KINDS.get(flow_name or "", CalibrationRunKind.WORKFLOW)


def automatic_objective(kind: CalibrationRunKind, run_name: str) -> str:
    """The objective text of an automatic session: what its first run launched."""
    label = {
        CalibrationRunKind.PIPELINE: "Pipeline",
        CalibrationRunKind.WORKFLOW: "Workflow",
        CalibrationRunKind.TASK: "Task",
        CalibrationRunKind.AGENT_ACTION: "Agent session",
    }[kind]
    return f"{label} {run_name}".strip() if run_name else label


def insert_or_load_automatic_session(
    *,
    calibration_session_id: str,
    project_id: str,
    chip_id: str,
    username: str,
    objective: str,
    child_count: int = 0,
) -> CalibrationSessionDocument:
    """Insert an automatic session, or load the one an earlier attempt inserted.

    The ID is derived from the request's key or the flow run, so a retry reaches the same
    session. One found with that ID must be an automatic session of the same project, chip,
    and user; anything else is refused rather than reused.
    """
    timestamp = now()
    doc = CalibrationSessionDocument(
        calibration_session_id=calibration_session_id,
        project_id=project_id,
        chip_id=chip_id,
        objective=objective,
        created_by=username,
        origin=CalibrationSessionOrigin.AUTOMATIC,
        child_count=child_count,
        created_at=timestamp,
        updated_at=timestamp,
    )
    try:
        doc.insert()
        return doc
    except DuplicateKeyError:
        existing = CalibrationSessionDocument.find_one(
            {"calibration_session_id": calibration_session_id}
        ).run()
    if existing is None:
        raise CalibrationRunMismatch(
            f"Calibration session {calibration_session_id} could not be recorded or read"
        )
    if (
        existing.project_id != project_id
        or existing.chip_id != chip_id
        or existing.created_by != username
        or existing.origin != CalibrationSessionOrigin.AUTOMATIC
    ):
        raise CalibrationRunMismatch(
            f"Calibration session {calibration_session_id} belongs to another project, chip, "
            "or user"
        )
    return existing


def read_identity(value: Any) -> CalibrationRunIdentity | None:
    """The run identity a flow-run context value names, or None for none or the marker."""
    if not isinstance(value, dict) or value.get(UNGROUPED_MARKER):
        return None
    return CalibrationRunIdentity.model_validate(value)


# Dispatch states in which the flow run QDash created for a run may still start: the launch
# is in flight, it returned, or QDash did not learn whether it created a flow run. A run QDash
# refused before creating one (``rejected``) is never carried out by a flow run.
_ADOPTABLE = (
    CalibrationPipelineRunStatus.DISPATCHING.value,
    CalibrationPipelineRunStatus.DISPATCHED.value,
    CalibrationPipelineRunStatus.UNKNOWN.value,
)


def adopt_recorded_run(
    identity: CalibrationRunIdentity,
    *,
    project_id: str,
    chip_id: str,
    username: str,
    flow_run_id: str,
) -> CalibrationRunIdentity:
    """Bind this flow run to the run the API recorded for it, or refuse.

    The run must exist in the project, on the chip, in the session named, and be requested by
    the user the flow run runs as. A run already bound to this flow run (the API settled the
    launch, or an earlier step bound it) is adopted. Otherwise the flow run must present the
    dispatch token of the launch attempt that holds the run, which the API generated and
    handed only to the flow run it created, and the binding is one conditional update: of
    flow runs presenting it at once, exactly one binds the run and every other is refused.
    A run bound to another flow run, refused before launch, or whose reservation was never
    admitted is never adopted. The dispatch status is left as the API recorded it.
    """
    run = CalibrationPipelineRunDocument.find_one(
        {"project_id": project_id, "run_id": identity.run_id}
    ).run()
    if run is None:
        raise CalibrationRunMismatch(
            f"Calibration run {identity.run_id} is not recorded in project {project_id}"
        )
    if run.calibration_session_id != identity.calibration_session_id or run.chip_id != chip_id:
        raise CalibrationRunMismatch(
            f"Calibration run {identity.run_id} belongs to session "
            f"{run.calibration_session_id} on chip {run.chip_id}, not to this flow run "
            f"on chip {chip_id}"
        )
    if run.requested_by != username:
        raise CalibrationRunMismatch(
            f"Calibration run {identity.run_id} was requested by another user than the one "
            f"flow run {flow_run_id} runs as"
        )
    if run.status == CalibrationPipelineRunStatus.REJECTED:
        raise CalibrationRunMismatch(
            f"QDash refused the launch of calibration run {identity.run_id} before creating "
            f"a flow run; flow run {flow_run_id} cannot carry it out"
        )
    if run.flow_run_id == flow_run_id:
        return identity
    if run.flow_run_id is not None:
        raise CalibrationRunMismatch(
            f"Calibration run {identity.run_id} is carried out by flow run {run.flow_run_id}, "
            f"not by flow run {flow_run_id}"
        )
    token = identity.dispatch_token
    if not token:
        # Fail closed: without the token the flow run cannot prove it is the one QDash
        # launched, and the API has not recorded which flow run that is yet.
        raise CalibrationRunMismatch(
            f"Flow run {flow_run_id} names calibration run {identity.run_id} without its "
            "dispatch token, and QDash has not recorded the run's flow run; the run is not "
            "adopted"
        )
    if not hmac.compare_digest(token, run.dispatch_token):
        raise CalibrationRunMismatch(
            f"Flow run {flow_run_id} does not hold the current launch of calibration run "
            f"{identity.run_id}"
        )
    if run.reservation_id is not None and _reservation_pending(run):
        raise CalibrationRunMismatch(
            f"Calibration run {identity.run_id} was not admitted to its session; flow run "
            f"{flow_run_id} cannot carry it out"
        )
    result = CalibrationPipelineRunDocument.get_motor_collection().update_one(
        {
            "project_id": project_id,
            "run_id": identity.run_id,
            "dispatch_token": token,
            "status": {"$in": list(_ADOPTABLE)},
            "flow_run_id": None,
        },
        {"$set": {"flow_run_id": flow_run_id}},
    )
    if result.matched_count == 0:
        bound = CalibrationPipelineRunDocument.find_one(
            {"project_id": project_id, "run_id": identity.run_id}
        ).run()
        if bound is None or bound.flow_run_id != flow_run_id:
            raise CalibrationRunMismatch(
                f"Calibration run {identity.run_id} was claimed by another flow run or "
                f"settled meanwhile; flow run {flow_run_id} cannot carry it out"
            )
    return identity


def _reservation_pending(run: CalibrationPipelineRunDocument) -> bool:
    """Whether the run's reservation is still pending: its launch was never admitted."""
    session = CalibrationSessionDocument.find_one(
        {"project_id": run.project_id, "calibration_session_id": run.calibration_session_id}
    ).run()
    if session is None:
        return True
    return any(
        reservation.reservation_id == run.reservation_id for reservation in session.pending_children
    )


def record_worker_run(
    *,
    project_id: str,
    chip_id: str,
    username: str,
    flow_run_id: str,
    flow_name: str | None,
    run_name: str,
    auto_scheduled: bool,
) -> CalibrationRunIdentity:
    """Record a flow run QDash did not launch, in an automatic session of its own.

    ``username`` is the user the flow run's parameters name, which QDash wrote into the
    deployment when the schedule was saved; it is never taken from a model or a client. Both
    records are keyed by the flow run, so a retry of the same flow run, or a later step of it,
    finds them instead of adding others.
    """
    kind = run_kind_of_flow(flow_name)
    session = insert_or_load_automatic_session(
        calibration_session_id=automatic_session_id_for_flow_run(flow_run_id),
        project_id=project_id,
        chip_id=chip_id,
        username=username,
        objective=automatic_objective(kind, run_name),
        child_count=1,
    )
    run_id = run_id_for_flow_run(flow_run_id)
    timestamp = now()
    run = CalibrationPipelineRunDocument(
        run_id=run_id,
        project_id=project_id,
        calibration_session_id=session.calibration_session_id,
        chip_id=chip_id,
        run_kind=kind,
        trigger=CalibrationRunTrigger.SCHEDULE if auto_scheduled else CalibrationRunTrigger.WORKER,
        run_name=run_name,
        idempotency_key=f"flow-run:{flow_run_id}",
        request_hash="",
        requested_by=username,
        status=CalibrationPipelineRunStatus.DISPATCHED,
        dispatch_token=f"worker:{flow_run_id}",
        pipeline_name=run_name if kind == CalibrationRunKind.PIPELINE else "",
        flow_run_id=flow_run_id,
        requested_at=timestamp,
        updated_at=timestamp,
    )
    try:
        run.insert()
    except DuplicateKeyError:
        existing = CalibrationPipelineRunDocument.find_one({"run_id": run_id}).run()
        if (
            existing is None
            or existing.project_id != project_id
            or existing.chip_id != chip_id
            or existing.requested_by != username
            or existing.flow_run_id != flow_run_id
        ):
            raise CalibrationRunMismatch(
                f"Calibration run {run_id} belongs to another project, chip, user, or flow run"
            ) from None
    return CalibrationRunIdentity(
        calibration_session_id=session.calibration_session_id, run_id=run_id
    )
