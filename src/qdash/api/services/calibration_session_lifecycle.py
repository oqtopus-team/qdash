"""Close automatic calibration sessions once everything started in them has ended.

QDash creates an automatic session for a run or agent session started without one. Such a
session has no person to close it, so QDash closes it when its work is over, and only then:

- Every run in it reached its end as a whole. A dispatched run has ended when Prefect reports a
  terminal state (completed, failed, cancelled, or crashed) for its whole flow run *in the
  check that closes the session*: the flow runs of a session are read again just before it is
  closed, and a state recorded by an earlier check is never trusted. A step execution that
  completed says nothing about the steps after it, and a flow run that is scheduled, awaiting a
  retry, late, pending, running, paused, or cancelling has not ended. A run whose flow run
  QDash never recorded, that Prefect does not report, or whose state could not be read has not
  ended either, even if an earlier check saw it end: nothing is inferred from the time, the
  step executions, their absence, or an earlier observation.
- No run is ``dispatching`` or ``unknown``: either may still start.
- No run (other than an agent action's) was ``rejected``: a refused launch may be retried with
  the same idempotency key, and that retry joins this session again. However old it is, such a
  run keeps the session open.
- Every agent session in it ended (completed, cancelled, or expired) and none of its
  measurements, commits, or backend applies is still in flight (``in_flight_operations``), or
  it was rejected and never operated.
- Nothing is being started in it (no reservation is pending), and something was recorded in
  it: a session whose first child is not written yet is never closed.

Each check first applies the recovery every read of a session applies
(``CalibrationSessionService.recover_stale_reservations``): a pipeline-run reservation pending
longer than ``RESERVATION_STALE_AFTER`` belongs to a request that stopped before launching, so
it is removed (the request, if only slow, then refuses to launch) and the run it holds, if
still ``dispatching``, is recorded ``rejected``. That rejected run then keeps the session open
as above. Agent-session reservations are never cleared here, and no unknown outcome is
acknowledged.

The close is the same conditional update a person's close is: on the child count and the
pending reservations read before the children. A run or agent session reserved in the session
meanwhile changes them, so the close does not happen and the new child is never lost; one
reserved after the close is refused as for any closed session. Prefect is not part of that
update: a flow run restarted between the final read and the close is not seen by it.

Closing is a grouping statement only. It cancels nothing, grants nothing, judges no run a
success, and is recorded as QDash's own (``close_origin`` ``automatic``, ``closed_by``
``SYSTEM_CLOSE_ACTOR``), with a note counting how the runs and agent sessions ended. Sessions a
person created (``origin`` ``manual``) are never closed here.

``RunDocument.flow_end_state`` is the state the latest such read found, for display: it is set
when Prefect reports a terminal state and cleared when Prefect reports the flow run running
again. Sessions that already closed are never read again.

Triggers: a periodic sweep in each API process visits open automatic sessions, least recently
checked first, and a detail read of one session checks it. Prefect is read only for sessions
nothing else keeps open, in batched requests, at most ``FLOW_RUNS_PER_READ *
MAX_FLOW_RUN_READS`` flow runs per check. A session whose flow runs do not fit in what is left
of that budget is left for the next sweep without being marked checked, so it comes first
then; sessions that were read are marked and go to the back. A missed completion, a worker or
API crash, or a session created before this existed is reconciled by a later check from the
records and Prefect alone.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from bunnet import SortDirection
from fastapi import HTTPException

from qdash.api.services.agent_execution_links import effective_session_status
from qdash.api.services.agent_session_gate import in_flight_operations, load_agent_session
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.api.services.run_ledger import dispatch_status
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentSessionStatus
from qdash.datamodel.calibration_session import (
    CalibrationAdmission,
    CalibrationChildKind,
    CalibrationSessionCloseOrigin,
    CalibrationSessionOrigin,
    CalibrationSessionStatus,
)
from qdash.datamodel.run import RunDispatchStatus, RunFlowEndState, RunKind
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import CalibrationSessionDocument
from qdash.dbmodel.run import RunDocument

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from datetime import datetime

logger = logging.getLogger("uvicorn.app")

# ``closed_by`` of an automatic close. A username cannot contain ``:``, so it names no user.
SYSTEM_CLOSE_ACTOR = "system:auto-close"
# Seconds between sweeps of one API process.
SWEEP_INTERVAL_SECONDS = 60.0
# Open automatic sessions one sweep checks.
SWEEP_BATCH = 50
# Flow runs one Prefect request reads, and requests one check makes at most. Sessions whose
# flow runs do not fit are read by a later check; they stay open meanwhile.
FLOW_RUNS_PER_READ = 200
MAX_FLOW_RUN_READS = 5
PREFECT_READ_TIMEOUT_SECONDS = 5.0
# How long shutdown waits for a sweep in progress to stop before the database is closed.
SHUTDOWN_WAIT_SECONDS = 10.0

# Prefect's terminal state types. Every other type (SCHEDULED, which includes AwaitingRetry
# and Late, PENDING, RUNNING, PAUSED, CANCELLING) means the flow run may still run.
_TERMINAL_PREFECT_STATES = {
    "COMPLETED": RunFlowEndState.COMPLETED,
    "FAILED": RunFlowEndState.FAILED,
    "CANCELLED": RunFlowEndState.CANCELLED,
    "CRASHED": RunFlowEndState.CRASHED,
}
_OPEN_AGENT_STATUSES = frozenset({AgentSessionStatus.ACTIVE, AgentSessionStatus.WAITING_FOR_HUMAN})


def read_prefect_flow_states(flow_run_ids: Sequence[str]) -> dict[str, str | None]:
    """The Prefect state type of each flow run, in one request.

    IDs that are not Prefect flow run IDs are skipped; a flow run Prefect does not report (it
    was deleted, or never existed) is absent. Raises when Prefect cannot be read.
    """
    uuids = [UUID(flow_run_id) for flow_run_id in flow_run_ids if _is_uuid(flow_run_id)]
    if not uuids:
        return {}
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterId

    with get_client(
        sync_client=True, httpx_settings={"timeout": PREFECT_READ_TIMEOUT_SECONDS}
    ) as client:
        runs = client.read_flow_runs(
            flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=uuids)),
            limit=len(uuids),
        )
    return {str(run.id): (run.state.type.value.upper() if run.state else None) for run in runs}


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


@dataclass
class LifecycleCheck:
    """What one check of an automatic session found."""

    calibration_session_id: str
    closed: bool = False
    # Why it stays open; empty when it was closed (or was already closed).
    waiting_on: list[str] = field(default_factory=list)


@dataclass
class _Ended:
    """How the children of a session whose work is over ended, for the closing note."""

    runs: Counter[str] = field(default_factory=Counter)
    agent_sessions: Counter[str] = field(default_factory=Counter)

    def note(self) -> str:
        parts = ["Closed automatically: everything started in this session ended."]
        if self.runs:
            parts.append(f"Runs: {_counts(self.runs)}.")
        if self.agent_sessions:
            parts.append(f"Agent sessions: {_counts(self.agent_sessions)}.")
        parts.append("Closing judges no outcome and cancels nothing.")
        return " ".join(parts)


def _counts(counter: Counter[str]) -> str:
    return ", ".join(f"{count} {label}" for label, count in sorted(counter.items()))


@dataclass(eq=False)
class _Candidate:
    """A session nothing but its flow runs keeps open, read before its children."""

    doc: CalibrationSessionDocument
    ended: _Ended
    # Dispatched runs bound to a flow run; Prefect is read for each before the close.
    flow_runs: list[RunDocument]

    @property
    def flow_run_ids(self) -> list[str]:
        return list(dict.fromkeys(str(run.flow_run_id) for run in self.flow_runs))


@dataclass
class _FlowStates:
    """What the Prefect reads of one check returned."""

    states: dict[str, str | None] = field(default_factory=dict)
    unreadable: set[str] = field(default_factory=set)


class CalibrationSessionLifecycle:
    """Check open automatic sessions and close those whose work has ended."""

    def __init__(
        self,
        read_flow_states: Callable[[Sequence[str]], Mapping[str, str | None]] | None = None,
    ) -> None:
        # Resolved at call time, so the module-level reader can be replaced in tests.
        self._read_flow_states = read_flow_states

    def sweep(
        self, *, limit: int = SWEEP_BATCH, stop: threading.Event | None = None
    ) -> list[LifecycleCheck]:
        """Check the ``limit`` open automatic sessions checked least recently."""
        docs: list[CalibrationSessionDocument] = (
            CalibrationSessionDocument.find(
                {
                    "status": CalibrationSessionStatus.OPEN.value,
                    "origin": CalibrationSessionOrigin.AUTOMATIC.value,
                }
            )
            .sort(
                [
                    ("lifecycle_checked_at", SortDirection.ASCENDING),
                    ("created_at", SortDirection.ASCENDING),
                ]
            )
            .limit(limit)
            .run()
        )
        return self.reconcile(docs, stop=stop)

    def reconcile(
        self,
        docs: Sequence[CalibrationSessionDocument],
        *,
        stop: threading.Event | None = None,
    ) -> list[LifecycleCheck]:
        """Close each open automatic session that is done; say what the others wait on.

        Manual sessions and sessions already closed are skipped. One check failing leaves its
        session open for the next one; it never stops the others. When ``stop`` is set the
        sessions not decided yet are left as they are, unmarked.
        """
        candidates = [doc for doc in docs if _automatic_and_open(doc)]
        checks: dict[int, LifecycleCheck] = {}
        ready: list[tuple[int, _Candidate]] = []
        for index, doc in enumerate(candidates):
            if _stopping(stop):
                checks[index] = _not_checked(doc, "the check was stopped")
                continue
            try:
                prepared = self._prepare(doc)
            except Exception:
                checks[index] = _failed(doc)
                continue
            if isinstance(prepared, LifecycleCheck):
                checks[index] = prepared
            else:
                ready.append((index, prepared))

        confirm, deferred = _within_budget([candidate for _, candidate in ready])
        flow_states = self._read_current(
            list(
                dict.fromkeys(
                    flow_run_id for candidate in confirm for flow_run_id in candidate.flow_run_ids
                )
            ),
            stop,
        )
        for index, candidate in ready:
            doc = candidate.doc
            if candidate in deferred:
                # Not marked checked, so the next sweep reaches it before the sessions read now.
                checks[index] = _not_checked(
                    doc, "its flow runs did not fit in this check's Prefect reads"
                )
                continue
            if _stopping(stop):
                checks[index] = _not_checked(doc, "the check was stopped")
                continue
            try:
                checks[index] = self._decide(candidate, flow_states)
            except Exception:
                checks[index] = _failed(doc)
        return [checks[index] for index in range(len(candidates))]

    # -- Internals -----------------------------------------------------------------------

    def _reader(self) -> Callable[[Sequence[str]], Mapping[str, str | None]]:
        return self._read_flow_states or read_prefect_flow_states

    def _prepare(self, listed: CalibrationSessionDocument) -> LifecycleCheck | _Candidate:
        """Read one session, then its children, and decide all but its flow runs.

        The session is read before its children, so a child reserved after this read changes
        ``child_count`` and makes the close in ``_decide`` match nothing.
        """
        session_id = listed.calibration_session_id
        doc = CalibrationSessionDocument.find_one(
            {"project_id": listed.project_id, "calibration_session_id": session_id}
        ).run()
        if doc is None or not _automatic_and_open(doc):
            return LifecycleCheck(calibration_session_id=session_id)
        # The recovery every read of a session applies (see the module docstring).
        doc = CalibrationSessionService.recover_stale_reservations(doc)
        waiting, ended, flow_runs = _children(doc)
        if waiting:
            _mark_checked(doc)
            return LifecycleCheck(calibration_session_id=session_id, waiting_on=waiting)
        if len({run.flow_run_id for run in flow_runs}) > _flow_run_budget():
            _mark_checked(doc)
            return LifecycleCheck(
                calibration_session_id=session_id,
                waiting_on=[
                    f"it has more flow runs than one check reads ({_flow_run_budget()}), "
                    "so it is not closed automatically"
                ],
            )
        return _Candidate(doc=doc, ended=ended, flow_runs=flow_runs)

    def _read_current(
        self, flow_run_ids: Sequence[str], stop: threading.Event | None
    ) -> _FlowStates:
        """Prefect's current state of each flow run, in batched requests.

        A batch that fails, or is not read because the check was stopped, leaves its flow
        runs unreadable, which keeps their sessions open.
        """
        found = _FlowStates()
        read = self._reader()
        for start in range(0, len(flow_run_ids), FLOW_RUNS_PER_READ):
            chunk = list(flow_run_ids[start : start + FLOW_RUNS_PER_READ])
            if _stopping(stop):
                found.unreadable.update(chunk)
                continue
            try:
                states = read(chunk)
            except Exception:
                logger.warning(
                    "Reading flow run states for automatic sessions failed", exc_info=True
                )
                found.unreadable.update(chunk)
                continue
            for flow_run_id in chunk:
                if flow_run_id in states:
                    found.states[flow_run_id] = states[flow_run_id]
        return found

    def _decide(self, candidate: _Candidate, flow_states: _FlowStates) -> LifecycleCheck:
        """Close one session if Prefect reports every flow run of it ended now."""
        doc = candidate.doc
        session_id = doc.calibration_session_id
        waiting: list[str] = []
        ended = candidate.ended
        observed_at = now()
        for run in candidate.flow_runs:
            flow_run_id = str(run.flow_run_id)
            label = f"run {run.run_id} (flow run {flow_run_id})"
            if flow_run_id in flow_states.unreadable:
                waiting.append(f"{label}: Prefect could not be read")
                continue
            if flow_run_id not in flow_states.states:
                # Kept as recorded: the flow run may have been deleted after it ended, but
                # nothing says so.
                waiting.append(
                    f"{label}: Prefect does not report it, so whether it ended is unknown"
                )
                continue
            state = str(flow_states.states[flow_run_id] or "").upper()
            end = _TERMINAL_PREFECT_STATES.get(state)
            _record_flow_state(run, end, observed_at)
            if end is None:
                waiting.append(
                    f"{label} has not ended: Prefect reports it {state.lower() or 'without a state'}"
                )
            else:
                ended.runs[end.value] += 1
        if waiting:
            _mark_checked(doc)
            return LifecycleCheck(calibration_session_id=session_id, waiting_on=waiting)
        return _close(doc, ended)


def _automatic_and_open(doc: CalibrationSessionDocument) -> bool:
    return (
        doc.origin == CalibrationSessionOrigin.AUTOMATIC
        and doc.status == CalibrationSessionStatus.OPEN
    )


def _stopping(stop: threading.Event | None) -> bool:
    return stop is not None and stop.is_set()


def _flow_run_budget() -> int:
    return FLOW_RUNS_PER_READ * MAX_FLOW_RUN_READS


def _within_budget(
    candidates: Sequence[_Candidate],
) -> tuple[list[_Candidate], list[_Candidate]]:
    """The sessions whose flow runs one check reads, in order, and the ones left for later.

    A session is read whole or not at all, so its close always rests on one read of every
    flow run in it.
    """
    confirm: list[_Candidate] = []
    deferred: list[_Candidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        new = [flow_run_id for flow_run_id in candidate.flow_run_ids if flow_run_id not in seen]
        if len(seen) + len(new) <= _flow_run_budget():
            confirm.append(candidate)
            seen.update(new)
        else:
            deferred.append(candidate)
    return confirm, deferred


def _not_checked(doc: CalibrationSessionDocument, reason: str) -> LifecycleCheck:
    return LifecycleCheck(calibration_session_id=doc.calibration_session_id, waiting_on=[reason])


def _failed(doc: CalibrationSessionDocument) -> LifecycleCheck:
    logger.exception("Checking automatic calibration session %s failed", doc.calibration_session_id)
    # Failed checks must yield their place, just like checks that find running work.
    # If MongoDB itself is unavailable, retain the failure without aborting other candidates.
    try:
        _mark_checked(doc)
    except Exception:
        logger.exception("Recording failed lifecycle check %s failed", doc.calibration_session_id)
    return _not_checked(doc, "the check failed")


def _mark_checked(doc: CalibrationSessionDocument) -> None:
    CalibrationSessionDocument.get_motor_collection().update_one(
        {"project_id": doc.project_id, "calibration_session_id": doc.calibration_session_id},
        {"$set": {"lifecycle_checked_at": now()}},
    )


def _record_flow_state(
    run: RunDocument, end: RunFlowEndState | None, observed_at: datetime
) -> None:
    """Record what Prefect reported now for the run's flow run, for display.

    Only for the flow run the record still names. A terminal state replaces whatever was
    recorded, and a state that is not terminal clears an end recorded earlier: the flow run
    was restarted or resumed.
    """
    recorded = run.flow_end_state
    if end == recorded:
        return
    update = (
        {"flow_end_state": None, "flow_end_observed_at": None}
        if end is None
        else {"flow_end_state": end.value, "flow_end_observed_at": observed_at}
    )
    RunDocument.get_motor_collection().update_one(
        {
            "project_id": run.project_id,
            "run_id": run.run_id,
            "flow_run_id": run.flow_run_id,
            "status": RunDispatchStatus.DISPATCHED.value,
        },
        {"$set": update},
    )


def _close(doc: CalibrationSessionDocument, ended: _Ended) -> LifecycleCheck:
    """The conditional close, on the session as it was read before its children."""
    session_id = doc.calibration_session_id
    timestamp = now()
    collection = CalibrationSessionDocument.get_motor_collection()
    scope = {"project_id": doc.project_id, "calibration_session_id": session_id}
    result = collection.update_one(
        {
            **scope,
            "status": CalibrationSessionStatus.OPEN.value,
            "origin": CalibrationSessionOrigin.AUTOMATIC.value,
            # No child was reserved, and none started or finished being started, since the
            # children were read.
            "child_count": doc.child_count,
            "pending_children": {"$size": 0},
        },
        {
            "$set": {
                "status": CalibrationSessionStatus.CLOSED.value,
                "closed_at": timestamp,
                "closed_by": SYSTEM_CLOSE_ACTOR,
                "close_origin": CalibrationSessionCloseOrigin.AUTOMATIC.value,
                "closing_note": ended.note(),
                "closed_with_unknown_runs": [],
                "closed_with_unknown_starts": [],
                "lifecycle_checked_at": timestamp,
                "updated_at": timestamp,
            }
        },
    )
    if result.modified_count == 1:
        logger.info("Closed automatic calibration session %s: its work ended", session_id)
        return LifecycleCheck(calibration_session_id=session_id, closed=True)
    # A child was reserved, or the session closed, meanwhile; the next check decides.
    _mark_checked(doc)
    return LifecycleCheck(
        calibration_session_id=session_id,
        waiting_on=["a child was started in it while it was being checked"],
    )


def _children(doc: CalibrationSessionDocument) -> tuple[list[str], _Ended, list[RunDocument]]:
    """What keeps the session open other than its flow runs, and the runs to read Prefect for.

    Read from every child, never a page of them.
    """
    waiting: list[str] = []
    ended = _Ended()
    flow_runs: list[RunDocument] = []
    for reservation in doc.pending_children:
        kind = "run" if reservation.kind == CalibrationChildKind.PIPELINE_RUN else "agent session"
        waiting.append(f"{kind} {reservation.child_id} is being started")
    scope = {"project_id": doc.project_id, "calibration_session_id": doc.calibration_session_id}
    runs: list[RunDocument] = (
        RunDocument.find(scope).sort([("requested_at", SortDirection.ASCENDING)]).run()
    )
    agents: list[AgentSessionDocument] = (
        AgentSessionDocument.find(scope).sort([("created_at", SortDirection.ASCENDING)]).run()
    )
    if not runs and not agents and not waiting:
        waiting.append("nothing has been recorded in it yet")
    for run in runs:
        reason = _run_waiting(run)
        if reason is not None:
            waiting.append(reason)
        elif dispatch_status(run) == RunDispatchStatus.DISPATCHED:
            flow_runs.append(run)
        else:
            ended.runs["not launched"] += 1
    for listed in agents:
        reason, outcome = _agent_waiting(doc.project_id, listed.session_id)
        if reason is not None:
            waiting.append(reason)
        elif outcome is not None:
            ended.agent_sessions[outcome] += 1
    return waiting, ended, flow_runs


def _run_waiting(run: RunDocument) -> str | None:
    """Why one run keeps its session open whatever Prefect reports, if it does.

    None for a run that will never start and for a dispatched run bound to a flow run, whose
    end only Prefect decides.
    """
    state = dispatch_status(run)
    if state == RunDispatchStatus.REJECTED:
        if run.run_kind == RunKind.AGENT_ACTION:
            # An agent action is dispatched once, by its agent session, which governs it.
            return None
        return (
            f"run {run.run_id} was refused before launch; a retry with its idempotency key "
            "launches it in this session"
        )
    if state == RunDispatchStatus.DISPATCHING:
        return f"run {run.run_id} is being dispatched"
    if state == RunDispatchStatus.UNKNOWN:
        return f"run {run.run_id} has an unknown dispatch outcome; it may be running"
    if not run.flow_run_id:
        return f"run {run.run_id} has no recorded flow run, so whether it ended is unknown"
    return None


def _agent_waiting(project_id: str, session_id: str) -> tuple[str | None, str | None]:
    """Why one agent session keeps its session open, or how it ended."""
    try:
        agent = load_agent_session(project_id, session_id)
    except HTTPException:
        return f"agent session {session_id} could not be read", None
    if agent.calibration_admission == CalibrationAdmission.PENDING:
        return f"agent session {session_id} is not admitted yet", None
    if agent.calibration_admission == CalibrationAdmission.REJECTED:
        # Rejected before it could operate: nothing ran in it.
        return None, "rejected"
    status_now = effective_session_status(agent.status, agent.expires_at)
    if status_now in _OPEN_AGENT_STATUSES:
        return f"agent session {session_id} is {status_now.value}", None
    operations = in_flight_operations(project_id, session_id)
    if operations:
        described = ", ".join(
            f"{op['kind'].replace('_', ' ')} {op['id']} is {op['status']}" for op in operations
        )
        return f"agent session {session_id} ended, but {described}", None
    return None, status_now.value


def run_lifecycle_sweeper(
    lifecycle: CalibrationSessionLifecycle | None = None,
    *,
    interval_seconds: float = SWEEP_INTERVAL_SECONDS,
) -> asyncio.Task[None]:
    """Start the loop that closes automatic sessions whose work ended.

    Each API process runs its own loop. Two loops checking the same session at once are safe:
    the close is one conditional update, and recording a flow run's state is idempotent.
    Cancelling the task asks a sweep in progress to stop between sessions and Prefect
    requests, and waits up to ``SHUTDOWN_WAIT_SECONDS`` for it, so await the cancelled task
    before closing the database.
    """
    checker = lifecycle or CalibrationSessionLifecycle()
    stop = threading.Event()

    async def sweep() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            running = asyncio.ensure_future(asyncio.to_thread(checker.sweep, stop=stop))
            try:
                await asyncio.shield(running)
            except asyncio.CancelledError:
                stop.set()
                await asyncio.wait({running}, timeout=SHUTDOWN_WAIT_SECONDS)
                if running.done() and not running.cancelled() and running.exception():
                    logger.warning("Automatic calibration session sweep failed while stopping")
                raise
            except Exception:
                logger.exception("Automatic calibration session sweep failed")

    return asyncio.get_running_loop().create_task(sweep())


def check_automatic_session(doc: CalibrationSessionDocument) -> None:
    """Check one session as a read of it does; a failure leaves it as it was."""
    if not _automatic_and_open(doc):
        return
    try:
        CalibrationSessionLifecycle().reconcile([doc])
    except Exception:
        logger.exception(
            "Checking automatic calibration session %s failed", doc.calibration_session_id
        )


__all__ = [
    "SYSTEM_CLOSE_ACTOR",
    "CalibrationSessionLifecycle",
    "LifecycleCheck",
    "check_automatic_session",
    "read_prefect_flow_states",
    "run_lifecycle_sweeper",
]
