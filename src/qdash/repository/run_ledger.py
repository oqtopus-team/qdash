"""The run ledger as the API and the workflow worker share it.

Every run QDash starts is one ``RunDocument``, and every step execution of the run carries
its ID in its note (``calibration_run_id``), with its calibration session's ID
(``calibration_session_id``) when it has one. The API records the run before it launches the
flow run and hands its identity, with the dispatch token of the launch attempt, to the worker
in the flow-run context (``RUN_CONTEXT_KEY``). The worker binds its flow run to the run only by
presenting that token, once: a flow run that only names a run's IDs claims nothing. A flow run
the API did not launch (a cron or one-time schedule, or a run started in Prefect directly)
carries none; the worker records it when the flow starts, with IDs derived from the flow run,
so a Prefect retry of the same flow run finds the same records instead of adding others.

Everything the worker checks is on the run: its project, chip, owner, admission, dispatch
token, and flow run. A calibration session is read only for a run recorded before runs
stored their admission, whose admission was then kept in the session.

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
from qdash.datamodel.run import (
    RunAdmission,
    RunAssociation,
    RunDispatchStatus,
    RunIdentity,
    RunKind,
    RunTrigger,
)
from qdash.dbmodel.run import LEGACY_SESSION_KEY_INDEX, RunDocument

# Prefect flow names of the system deployments, and the kind of run each launches. Any other
# flow is a saved workflow.
SYSTEM_FLOW_KINDS = {
    "calibration-pipeline": RunKind.PIPELINE,
    "single-task-executor": RunKind.TASK,
}
# Execution note keys the worker stamps on every step execution of a run.
NOTE_SESSION_KEY = "calibration_session_id"
NOTE_RUN_KEY = "calibration_run_id"
# The value of the context key for a launch QDash deliberately records no run for: an action
# of an agent session created before runs were recorded for agent actions, whose executions
# stay in that agent session alone.
UNGROUPED_MARKER = "ungrouped"


class RunMismatch(RuntimeError):
    """A recorded run or session does not belong to the project, chip, or user at hand."""


class RunScopeIndexConflict(RuntimeError):
    """A run without a calibration session hit the unique index of the earlier run scope.

    That index (``LEGACY_SESSION_KEY_INDEX``) holds every run without a session to one
    shared null session. Runs QDash records without a session today (actions of an agent
    session that has none) are keyed by their action, so they do not collide on it; this
    reports a collision as itself, instead of as a concurrent retry, should one occur.
    Nothing was recorded or launched.
    """


def digest(*parts: str) -> str:
    """A short stable digest of ``parts``, which never collides by concatenation."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


def key_scope(username: str, idempotency_key: str) -> str:
    """The scope a request's key is retried in: the signed-in user and the key.

    The kind of run, the chip, and the calibration session are not part of it; they are part
    of the request hash, so the same key for another request is refused, not launched.
    """
    return f"key:{digest(username, idempotency_key)}"


def flow_run_scope(flow_run_id: str) -> str:
    """The scope of the run the worker records for a flow run QDash did not launch."""
    return f"flow-run:{flow_run_id}"


def agent_action_scope(action_id: str) -> str:
    """The scope of the run an agent action's dispatch records."""
    return f"agent-action:{action_id}"


def run_id_for_flow_run(flow_run_id: str) -> str:
    """The run the worker records for a flow run QDash did not launch."""
    return f"cpr-flow-{flow_run_id}"


def run_kind_of_flow(flow_name: str | None) -> RunKind:
    """The kind of run a Prefect flow launches, from its flow name."""
    return SYSTEM_FLOW_KINDS.get(flow_name or "", RunKind.WORKFLOW)


def insert_run(doc: RunDocument) -> None:
    """Insert a run; a run without a session refused by the earlier index says so."""
    try:
        doc.insert()
    except DuplicateKeyError as exc:
        # Another run holding this run's ID or scope is a concurrent attempt of the same
        # request, whichever index reported it first; only a collision with nothing holding
        # either is the earlier index refusing a run without a session.
        if doc.calibration_session_id is None and not _held(doc):
            raise RunScopeIndexConflict(
                f"Run {doc.run_id} joins no calibration session, and the unique index "
                f"{LEGACY_SESSION_KEY_INDEX} of the earlier run scope refuses it. Nothing was "
                "started."
            ) from exc
        raise


def _held(doc: RunDocument) -> bool:
    """Whether another run holds this run's ID or scope: the indexes a run is unique by."""
    clauses: list[dict[str, Any]] = [{"run_id": doc.run_id}]
    if doc.idempotency_scope is not None:
        clauses.append({"project_id": doc.project_id, "idempotency_scope": doc.idempotency_scope})
    return RunDocument.find_one({"$or": clauses}).run() is not None


def read_identity(value: Any) -> RunIdentity | None:
    """The run identity a flow-run context value names, or None for none or the marker."""
    if not isinstance(value, dict) or value.get(UNGROUPED_MARKER):
        return None
    return RunIdentity.model_validate(value)


# Dispatch states in which the flow run QDash created for a run may still start: the launch
# is in flight, it returned, or QDash did not learn whether it created a flow run. A run QDash
# refused before creating one (``rejected``) is never carried out by a flow run.
_ADOPTABLE = (
    RunDispatchStatus.DISPATCHING.value,
    RunDispatchStatus.DISPATCHED.value,
    RunDispatchStatus.UNKNOWN.value,
)


def bind_flow_run(
    identity: RunIdentity,
    *,
    project_id: str,
    chip_id: str,
    username: str,
    flow_run_id: str,
) -> RunIdentity:
    """Bind this flow run to the run the API recorded for it, or refuse.

    The run must exist in the project, on the chip, with the calibration session (or none)
    the identity names, and be requested by the user the flow run runs as. A run already
    bound to this flow run (the API settled the launch, or an earlier step bound it) is
    adopted. Otherwise the flow run must present the dispatch token of the launch attempt that
    holds the run, which the API generated and handed only to the flow run it created, the
    attempt must be admitted, and the binding is one conditional update: of flow runs
    presenting it at once, exactly one binds the run and every other is refused. A run bound
    to another flow run, refused before launch, or whose attempt was never admitted is never
    adopted. The dispatch status is left as the API recorded it.
    """
    run = RunDocument.find_one({"project_id": project_id, "run_id": identity.run_id}).run()
    if run is None:
        raise RunMismatch(f"Run {identity.run_id} is not recorded in project {project_id}")
    if run.calibration_session_id != identity.calibration_session_id or run.chip_id != chip_id:
        raise RunMismatch(
            f"Run {identity.run_id} belongs to calibration session "
            f"{run.calibration_session_id or '(none)'} on chip {run.chip_id}, not to this flow "
            f"run on chip {chip_id}"
        )
    if run.requested_by != username:
        raise RunMismatch(
            f"Run {identity.run_id} was requested by another user than the one flow run "
            f"{flow_run_id} runs as"
        )
    if run.status == RunDispatchStatus.REJECTED:
        raise RunMismatch(
            f"QDash refused the launch of run {identity.run_id} before creating a flow run; "
            f"flow run {flow_run_id} cannot carry it out"
        )
    if run.flow_run_id == flow_run_id:
        return identity
    if run.flow_run_id is not None:
        raise RunMismatch(
            f"Run {identity.run_id} is carried out by flow run {run.flow_run_id}, not by "
            f"flow run {flow_run_id}"
        )
    token = identity.dispatch_token
    if not token:
        # Fail closed: without the token the flow run cannot prove it is the one QDash
        # launched, and the API has not recorded which flow run that is yet.
        raise RunMismatch(
            f"Flow run {flow_run_id} names run {identity.run_id} without its dispatch token, "
            "and QDash has not recorded the run's flow run; the run is not adopted"
        )
    if not hmac.compare_digest(token, run.dispatch_token):
        raise RunMismatch(
            f"Flow run {flow_run_id} does not hold the current launch of run {identity.run_id}"
        )
    if not _admitted(run):
        raise RunMismatch(
            f"The launch of run {identity.run_id} was not admitted; flow run {flow_run_id} "
            "cannot carry it out"
        )
    result = RunDocument.get_motor_collection().update_one(
        {
            "project_id": project_id,
            "run_id": identity.run_id,
            "dispatch_token": token,
            "status": {"$in": list(_ADOPTABLE)},
            "flow_run_id": None,
            # Never a pending attempt, even if it became one after the read above.
            "admission": {"$ne": RunAdmission.PENDING.value},
        },
        {"$set": {"flow_run_id": flow_run_id}},
    )
    if result.matched_count == 0:
        bound = RunDocument.find_one({"project_id": project_id, "run_id": identity.run_id}).run()
        if bound is None or bound.flow_run_id != flow_run_id:
            raise RunMismatch(
                f"Run {identity.run_id} was claimed by another flow run or settled meanwhile; "
                f"flow run {flow_run_id} cannot carry it out"
            )
    return identity


def _admitted(run: RunDocument) -> bool:
    """Whether the attempt that holds the run may be carried out, read from the run.

    A run recorded before admission was stored (``admission`` None) with a reservation was
    admitted when that reservation left its session's pending list; that is still read from
    the session, the only place it was kept, and a session that cannot be read refuses it.
    """
    if run.admission is not None:
        return run.admission == RunAdmission.ADMITTED
    if run.reservation_id is None:
        return True
    from qdash.dbmodel.calibration_session import CalibrationSessionDocument

    session = CalibrationSessionDocument.find_one(
        {"project_id": run.project_id, "calibration_session_id": run.calibration_session_id}
    ).run()
    if session is None:
        return False
    return all(
        reservation.reservation_id != run.reservation_id for reservation in session.pending_children
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
    session_name: str | None = None,
) -> RunIdentity:
    """Record a flow run QDash did not launch, in an automatic session of its own.

    ``session_name`` names that session (the flow's ``@calibration_flow(session_name=...)``)
    instead of the default named after the run; a session already recorded for the flow run
    keeps its name.

    ``username`` is the user the flow run's parameters name, which QDash wrote into the
    deployment when the schedule was saved; it is never taken from a model or a client. The
    records are keyed by the flow run, so a retry of the same flow run, or a later step of it,
    finds them instead of adding others. A run already recorded for the flow run keeps the
    session it was recorded with, or none if it was recorded without one.
    """
    run_id = run_id_for_flow_run(flow_run_id)
    existing = RunDocument.find_one({"run_id": run_id}).run()
    if existing is not None:
        return _recorded_worker_run(existing, project_id, chip_id, username, flow_run_id)

    kind = run_kind_of_flow(flow_name)
    from qdash.repository.calibration_run import (
        automatic_objective,
        automatic_session_id_for_flow_run,
        insert_or_load_automatic_session,
    )

    calibration_session_id = insert_or_load_automatic_session(
        calibration_session_id=automatic_session_id_for_flow_run(flow_run_id),
        project_id=project_id,
        chip_id=chip_id,
        username=username,
        objective=session_name or automatic_objective(kind, run_name),
        child_count=1,
    ).calibration_session_id
    timestamp = now()
    run = RunDocument(
        run_id=run_id,
        project_id=project_id,
        calibration_session_id=calibration_session_id,
        association=RunAssociation.AUTOMATIC,
        chip_id=chip_id,
        run_kind=kind,
        trigger=RunTrigger.SCHEDULE if auto_scheduled else RunTrigger.WORKER,
        run_name=run_name,
        idempotency_key=flow_run_scope(flow_run_id),
        idempotency_scope=flow_run_scope(flow_run_id),
        request_hash="",
        requested_by=username,
        status=RunDispatchStatus.DISPATCHED,
        dispatch_token=f"worker:{flow_run_id}",
        admission=RunAdmission.ADMITTED,
        pipeline_name=run_name if kind == RunKind.PIPELINE else "",
        flow_run_id=flow_run_id,
        requested_at=timestamp,
        updated_at=timestamp,
    )
    try:
        insert_run(run)
    except DuplicateKeyError:
        found = RunDocument.find_one({"run_id": run_id}).run()
        if found is None:
            raise RunMismatch(f"Run {run_id} could not be recorded or read") from None
        return _recorded_worker_run(found, project_id, chip_id, username, flow_run_id)
    return RunIdentity(calibration_session_id=calibration_session_id, run_id=run_id)


def _recorded_worker_run(
    existing: RunDocument, project_id: str, chip_id: str, username: str, flow_run_id: str
) -> RunIdentity:
    if (
        existing.project_id != project_id
        or existing.chip_id != chip_id
        or existing.requested_by != username
        or existing.flow_run_id != flow_run_id
    ):
        raise RunMismatch(
            f"Run {existing.run_id} belongs to another project, chip, user, or flow run"
        )
    return RunIdentity(
        calibration_session_id=existing.calibration_session_id, run_id=existing.run_id
    )
