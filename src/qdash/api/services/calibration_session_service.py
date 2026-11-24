"""Calibration sessions: one objective, the runs and agent sessions started for it.

A calibration session is a record of purpose. It grants no operation and controls none: an
agent session keeps its own policy, gates, expiry, and pause, and a run keeps the approval of
its exact request, its own admission and dispatch record (``qdash.api.services.run_ledger``),
and the execution lock. What this module adds is the explicit relation, written only when a
child is started with the session's ID:

- An agent session stores ``calibration_session_id`` in its own record when it is created.
- A run stores it in its ``RunDocument``, inserted before the flow run is created. Its step
  executions carry the run's ID, never found by the earliest execution, a tag, the chip, or
  the time.

Every relation is checked here, in the request's project: the session exists there, it is
open, it is on the child's chip, and the signed-in user created it. Mongo runs standalone, so
each state change is one conditional update of one document. A child is therefore started in
three steps: a reservation pushed into the open session together with its count, the child's
own record (carrying the reservation), and the removal of the reservation by the same request.
A pipeline run is launched only after that removal succeeded. Closing reads every child (never
the page a detail response shows), refuses while a recent reservation is pending, and clears
the older ones in the same conditional update that closes; a request whose reservation was
cleared undoes its child instead of starting it.

The removal is the child's admission, and it is irrevocable:

- An agent session is written with ``calibration_admission`` ``pending`` and refused by every
  operational gate until the removal lists its reservation in ``admitted_reservation_ids``.
  An agent session whose reservation a close cleared is rejected and never operates, however
  late its record is written, and a crash after the removal is recovered from that list.
- A run whose removal succeeded is admitted, and its request records that on the run before
  launching it. Its request may stall before the launch and launch after the session was
  closed with its outcome acknowledged as unknown: closing cancels nothing that was admitted,
  and the run stays recorded in the session. The worker reads the admission from the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from bunnet import SortDirection
from fastapi import HTTPException, status

from qdash.api.schemas.calibration_session import (
    CalibrationAgentSessionChild,
    CalibrationPipelineRunResponse,
    CalibrationSessionDetailResponse,
    CalibrationSessionResponse,
    CloseCalibrationSessionRequest,
    CreateCalibrationSessionRequest,
    ListCalibrationSessionsResponse,
)
from qdash.api.services.agent_execution_links import (
    OPEN_EXECUTION_STATUSES,
    effective_session_status,
    resolve_chip_links,
    utc,
)
from qdash.api.services.agent_session_gate import (
    in_flight_operations,
    load_agent_session,
    reject_calibration_child,
)
from qdash.api.services.execution_service import execution_summary
from qdash.api.services.run_ledger import (
    DISPATCH_STALE_AFTER,
    PipelineDispatch,
    RunDispatch,
    dispatch_status,
    pipeline_request_hash,
    run_request_hash,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentSessionStatus, model_label
from qdash.datamodel.calibration_session import (
    CalibrationAdmission,
    CalibrationChildKind,
    CalibrationChildReservation,
    CalibrationPipelineRunStatus,
    CalibrationRunKind,
    CalibrationSessionCloseOrigin,
    CalibrationSessionOrigin,
    CalibrationSessionStatus,
)
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.repository.run_ledger import NOTE_RUN_KEY

if TYPE_CHECKING:
    from qdash.api.services.execution_service import ExecutionService

# Run hashing and dispatch reads live with the run ledger; re-exported for their callers.
__all__ = [
    "DISPATCH_STALE_AFTER",
    "CalibrationSessionService",
    "CloseBlockers",
    "PipelineDispatch",
    "RunDispatch",
    "calibration_session_closed",
    "dispatch_status",
    "execution_scope_of_run",
    "pipeline_request_hash",
    "run_request_hash",
]

logger = logging.getLogger("uvicorn.app")

# A reservation older than this whose child was never recorded belongs to a request that
# stopped (or hangs) between counting the child and writing it.
RESERVATION_STALE_AFTER = DISPATCH_STALE_AFTER
# Pipeline runs and agent sessions one detail response lists: the most recent ones, oldest
# first. Close blockers never depend on this page; they are read from every child.
MAX_DETAIL_CHILDREN = 100
OPEN_AGENT_STATUSES = frozenset({AgentSessionStatus.ACTIVE, AgentSessionStatus.WAITING_FOR_HUMAN})
UNADMITTED_ADMISSIONS = frozenset({CalibrationAdmission.PENDING, CalibrationAdmission.REJECTED})
# Runs a session lists, counts, and checks before closing. An agent action's run is shown,
# counted, and checked through its agent session, which governs its dispatch.
LISTED_RUNS = {"run_kind": {"$ne": CalibrationRunKind.AGENT_ACTION.value}}


def execution_scope_of_run(run: CalibrationPipelineRunDocument) -> dict[str, Any]:
    """The query for a run's step executions on its chip.

    The worker stamps ``note.calibration_run_id`` on each; a run recorded before that note
    existed is found by its flow run.
    """
    clauses: list[dict[str, Any]] = [{f"note.{NOTE_RUN_KEY}": run.run_id}]
    if run.flow_run_id:
        # Only an execution without the stamp is found by its flow run.
        clauses.append(
            {"note.flow_run_id": run.flow_run_id, f"note.{NOTE_RUN_KEY}": {"$exists": False}}
        )
    return {"project_id": run.project_id, "chip_id": run.chip_id, "$or": clauses}


def _response(doc: CalibrationSessionDocument) -> CalibrationSessionResponse:
    return CalibrationSessionResponse.model_validate(doc.model_dump())


def _reservation_stale(reservation: CalibrationChildReservation) -> bool:
    reserved = utc(reservation.reserved_at)
    return reserved is not None and now() - reserved > RESERVATION_STALE_AFTER


def _child_label(reservation: CalibrationChildReservation) -> str:
    if reservation.kind == CalibrationChildKind.PIPELINE_RUN:
        return f"run {reservation.child_id}"
    return f"agent session {reservation.child_id}"


def calibration_session_closed(calibration_session_id: str) -> HTTPException:
    """The refusal of a child whose calibration session is closed."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Calibration session {calibration_session_id} is closed; start a new one",
    )


class CalibrationSessionService:
    """Create, read, and close calibration sessions, and relate children to them."""

    def __init__(self, execution_service: ExecutionService | None = None) -> None:
        self._executions = execution_service

    # -- Sessions ------------------------------------------------------------------------

    def create(
        self, *, project_id: str, username: str, body: CreateCalibrationSessionRequest
    ) -> CalibrationSessionResponse:
        """Record a new objective on a chip of the project."""
        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": body.chip_id}).run()
        if chip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chip '{body.chip_id}' not found",
            )
        timestamp = now()
        doc = CalibrationSessionDocument(
            calibration_session_id=f"cs-{uuid4()}",
            project_id=project_id,
            chip_id=body.chip_id,
            objective=body.objective.strip() or body.objective,
            created_by=username,
            created_at=timestamp,
            updated_at=timestamp,
        )
        doc.insert()
        return _response(doc)

    def list_sessions(
        self,
        *,
        project_id: str,
        chip_id: str | None = None,
        created_by: str | None = None,
        statuses: list[CalibrationSessionStatus] | None = None,
        origins: list[CalibrationSessionOrigin] | None = None,
        limit: int = 20,
        skip: int = 0,
    ) -> ListCalibrationSessionsResponse:
        """The project's calibration sessions, newest first, ``limit`` after ``skip``."""
        query: dict[str, Any] = {"project_id": project_id}
        if chip_id:
            query["chip_id"] = chip_id
        if created_by:
            query["created_by"] = created_by
        if statuses:
            query["status"] = {"$in": sorted({value.value for value in statuses})}
        if origins:
            wanted = sorted({value.value for value in origins})
            if CalibrationSessionOrigin.MANUAL in origins:
                # Sessions recorded before ``origin`` existed were all created by a person.
                query["$or"] = [{"origin": {"$in": wanted}}, {"origin": {"$exists": False}}]
            else:
                query["origin"] = {"$in": wanted}
        # One extra row says whether another page follows, without counting every session.
        docs = list(
            CalibrationSessionDocument.find(query)
            .sort(
                [
                    ("created_at", SortDirection.DESCENDING),
                    ("calibration_session_id", SortDirection.DESCENDING),
                ]
            )
            .skip(skip)
            .limit(limit + 1)
            .run()
        )
        items = [_response(doc) for doc in docs[:limit]]
        return ListCalibrationSessionsResponse(
            items=items, total=len(items), skip=skip, has_more=len(docs) > limit
        )

    def get(
        self, *, project_id: str, calibration_session_id: str
    ) -> CalibrationSessionDetailResponse:
        """A calibration session with its most recent pipeline runs and agent sessions.

        ``close_blockers`` and the unknown lists are read from every child, not only the ones
        listed; ``pipeline_run_total`` and ``agent_session_total`` count every child. An open
        automatic session is first checked, and closed if everything started in it ended
        (``calibration_session_lifecycle``).
        """
        doc = self._load(project_id, calibration_session_id)
        if (
            doc.origin == CalibrationSessionOrigin.AUTOMATIC
            and doc.status == CalibrationSessionStatus.OPEN
        ):
            # Imported here: the lifecycle check builds on this service.
            from qdash.api.services.calibration_session_lifecycle import check_automatic_session

            check_automatic_session(doc)
            doc = self._load(project_id, calibration_session_id)
        doc = self._recover_pipeline_reservations(doc)
        return self._detail(doc, self._blockers(doc))

    def close(
        self,
        *,
        project_id: str,
        calibration_session_id: str,
        username: str,
        body: CloseCalibrationSessionRequest,
    ) -> CalibrationSessionDetailResponse:
        """End work on the objective once nothing started in the session still runs or waits.

        Closing stops nothing and judges nothing: it only refuses new children. It reads every
        child, and is refused while one runs or waits, while a child is being started, and,
        unless the person acknowledges them, while a pipeline run's dispatch outcome or an
        agent session's start is unknown. The close itself is one conditional update on the
        child count and the pending reservations it read, so a child started or recorded
        between that check and the close makes the close fail.

        An acknowledged pipeline run was admitted and may still start after the close; the
        close does not cancel it. An acknowledged agent start was never admitted: if its
        session is written later it is rejected and never operates. An agent session whose
        older reservation is still pending is rejected by the close, without acknowledgment,
        because nothing can have run in it.
        """
        doc = self._owned(project_id, calibration_session_id, username)
        if doc.status == CalibrationSessionStatus.CLOSED:
            return self.get(project_id=project_id, calibration_session_id=calibration_session_id)
        # The session is read before its children, so a child counted after this read changes
        # ``child_count`` and one recorded after it changes ``pending_children``.
        doc = self._recover_pipeline_reservations(doc)
        seen_children = doc.child_count
        pending = list(doc.pending_children)
        blockers = self._blockers(doc)
        if blockers.blockers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The calibration session still has work that runs, waits, or is being "
                    "started: " + "; ".join(blockers.blockers)
                ),
            )
        if (blockers.unknown_runs or blockers.unknown_starts) and not (
            body.acknowledge_unknown_runs
        ):
            parts: list[str] = []
            if blockers.unknown_runs:
                parts.append(
                    ", ".join(f"pipeline run {run_id}" for run_id in blockers.unknown_runs)
                    + ": admitted, and the launch outcome is unknown; they may be running, "
                    "or may still start after the close, which does not cancel them. Check "
                    "the Execution list."
                )
            if blockers.unknown_starts:
                parts.append(
                    ", ".join(f"agent session {r.child_id}" for r in blockers.unknown_starts)
                    + ": the start was never finalized, so one recorded later is rejected "
                    "and never operates."
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=" ".join(parts) + " Close with acknowledge_unknown_runs to proceed.",
            )
        timestamp = now()
        result = CalibrationSessionDocument.get_motor_collection().update_one(
            {
                "calibration_session_id": calibration_session_id,
                "project_id": project_id,
                "status": CalibrationSessionStatus.OPEN.value,
                "child_count": seen_children,
                # No reservation was added (the count) or removed since they were read.
                "pending_children": {"$size": len(pending)},
            },
            {
                "$set": {
                    "status": CalibrationSessionStatus.CLOSED.value,
                    "closed_at": timestamp,
                    "closed_by": username,
                    "close_origin": CalibrationSessionCloseOrigin.MANUAL.value,
                    "closing_note": body.closing_note,
                    "closed_with_unknown_runs": blockers.unknown_runs,
                    "closed_with_unknown_starts": [
                        _reservation_bson(r) for r in blockers.unknown_starts
                    ],
                    "pending_children": [],
                    "updated_at": timestamp,
                }
            },
        )
        if result.matched_count == 0:
            current = self._load(project_id, calibration_session_id)
            if current.status != CalibrationSessionStatus.CLOSED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A run was started in the calibration session while closing it; "
                    "check it and close again",
                )
        else:
            for reservation in pending:
                if reservation.kind == CalibrationChildKind.PIPELINE_RUN:
                    _reject_unlaunched_run(reservation)
                else:
                    _reject_unadmitted_agent(project_id, reservation, actor=username)
        return self.get(project_id=project_id, calibration_session_id=calibration_session_id)

    # -- Relations -----------------------------------------------------------------------

    def reserve_child(
        self,
        *,
        project_id: str,
        calibration_session_id: str,
        chip_id: str,
        username: str,
        kind: CalibrationChildKind,
        child_id: str,
    ) -> CalibrationChildReservation:
        """Check that a child may start in the session, and reserve it before it is written.

        The session must be in this project, open, on the child's chip, and created by the
        signed-in user. The reservation is pushed, and the count raised, on the condition that
        the session is still open, so a session closed meanwhile refuses the child and a close
        that follows sees it. The caller writes the child with ``child_id``, then calls
        ``finalize_child``; on a failure known to have written nothing, ``release_child``.
        """
        doc = self._owned(project_id, calibration_session_id, username)
        if doc.chip_id != chip_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Calibration session {calibration_session_id} is on chip {doc.chip_id}, "
                    f"not {chip_id}"
                ),
            )
        reservation = CalibrationChildReservation(
            reservation_id=f"csr-{uuid4()}",
            kind=kind,
            child_id=child_id,
            reserved_by=username,
            reserved_at=now(),
        )
        result = CalibrationSessionDocument.get_motor_collection().update_one(
            {
                "calibration_session_id": calibration_session_id,
                "project_id": project_id,
                "status": CalibrationSessionStatus.OPEN.value,
            },
            {
                "$push": {"pending_children": _reservation_bson(reservation)},
                "$inc": {"child_count": 1},
                "$set": {"updated_at": reservation.reserved_at},
            },
        )
        if result.matched_count == 0:
            raise calibration_session_closed(calibration_session_id)
        return reservation

    @staticmethod
    def finalize_child(
        *,
        project_id: str,
        calibration_session_id: str,
        reservation_id: str,
        admit: bool = False,
    ) -> bool:
        """Remove a reservation whose child is now recorded; False when a close cleared it.

        A False answer means the session was closed (or the reservation recovered as never
        started) before the child was recorded: the caller must undo the child, not start it.
        With ``admit`` (an agent session), the same update lists the reservation in
        ``admitted_reservation_ids``: the durable proof the agent session's admission is read
        from, so a crash before the agent session records it loses nothing.
        """
        update: dict[str, Any] = {
            "$pull": {"pending_children": {"reservation_id": reservation_id}},
            "$set": {"updated_at": now()},
        }
        if admit:
            update["$addToSet"] = {"admitted_reservation_ids": reservation_id}
        result = CalibrationSessionDocument.get_motor_collection().update_one(
            {
                "calibration_session_id": calibration_session_id,
                "project_id": project_id,
                "pending_children.reservation_id": reservation_id,
            },
            update,
        )
        return result.matched_count == 1

    def release_child(
        self, *, project_id: str, calibration_session_id: str, reservation_id: str
    ) -> None:
        """Remove the reservation of a child known not to have been written or started."""
        try:
            self.finalize_child(
                project_id=project_id,
                calibration_session_id=calibration_session_id,
                reservation_id=reservation_id,
            )
        except Exception:
            # It stays pending: a close refuses it while recent and reports it after.
            logger.exception(
                "Failed to release reservation %s of calibration session %s",
                reservation_id,
                calibration_session_id,
            )

    # -- Association, as the run ledger uses it ---------------------------------------------

    def load(self, project_id: str, calibration_session_id: str) -> CalibrationSessionDocument:
        """The session in the project, or 404."""
        return self._load(project_id, calibration_session_id)

    def owned(
        self, project_id: str, calibration_session_id: str, username: str
    ) -> CalibrationSessionDocument:
        """The session in the project, created by ``username``; 404 or 403 otherwise."""
        return self._owned(project_id, calibration_session_id, username)

    def recover_reservations(self, project_id: str, calibration_session_id: str) -> None:
        """Reject runs whose request stopped before launching them; nothing if none is found."""
        doc = CalibrationSessionDocument.find_one(
            {"project_id": project_id, "calibration_session_id": calibration_session_id}
        ).run()
        if doc is not None:
            self._recover_pipeline_reservations(doc)

    @staticmethod
    def recover_stale_reservations(
        doc: CalibrationSessionDocument,
    ) -> CalibrationSessionDocument:
        """Reject pipeline runs whose request stopped before launching them; the session after."""
        return CalibrationSessionService._recover_pipeline_reservations(doc)

    @staticmethod
    def reject_unlaunched(reservation: CalibrationChildReservation) -> None:
        """Record the run of a reservation that will never launch as ``rejected``."""
        _reject_unlaunched_run(reservation)

    @staticmethod
    def closed(calibration_session_id: str) -> HTTPException:
        """The refusal of a run whose session was closed before it was admitted."""
        return calibration_session_closed(calibration_session_id)

    # -- Internals -----------------------------------------------------------------------

    @staticmethod
    def _load(project_id: str, calibration_session_id: str) -> CalibrationSessionDocument:
        doc = CalibrationSessionDocument.find_one(
            {"project_id": project_id, "calibration_session_id": calibration_session_id}
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calibration session '{calibration_session_id}' not found",
            )
        return doc

    def _owned(
        self, project_id: str, calibration_session_id: str, username: str
    ) -> CalibrationSessionDocument:
        doc = self._load(project_id, calibration_session_id)
        if doc.created_by != username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Calibration session {calibration_session_id} was created by "
                    f"{doc.created_by}; only they can start or close work in it"
                ),
            )
        return doc

    def _detail(
        self, doc: CalibrationSessionDocument, blockers: CloseBlockers
    ) -> CalibrationSessionDetailResponse:
        scope = {"project_id": doc.project_id, "calibration_session_id": doc.calibration_session_id}
        from qdash.api.services.calibration_session_audit import CalibrationSessionAuditService

        search = CalibrationSessionAuditService().search(doc)
        return CalibrationSessionDetailResponse(
            **_response(doc).model_dump(),
            experiments=search.experiments,
            decisions=search.decisions,
            decision_total=search.decision_total,
            recommendation=search.recommendation,
            latest_requested_run=search.latest_requested_run,
            pipeline_runs=[self._run_response(run) for run in self._recent_runs(doc)],
            pipeline_run_total=CalibrationPipelineRunDocument.find(
                {**scope, **LISTED_RUNS}
            ).count(),
            agent_sessions=self._agent_children(doc),
            agent_session_total=AgentSessionDocument.find(scope).count(),
            close_blockers=blockers.blockers,
            unknown_runs=blockers.unknown_runs,
            unknown_starts=blockers.unknown_starts,
        )

    @staticmethod
    def _recover_pipeline_reservations(
        doc: CalibrationSessionDocument,
    ) -> CalibrationSessionDocument:
        """Reject pipeline runs whose request stopped before launching them.

        A pipeline run is launched only by the request that removed its reservation, so a
        reservation still pending long after it was made belongs to a launch that never
        happened. Removing it first makes that request, if it is only slow, find it gone and
        refuse to launch.
        """
        stale = [
            reservation
            for reservation in doc.pending_children
            if reservation.kind == CalibrationChildKind.PIPELINE_RUN
            and _reservation_stale(reservation)
        ]
        if not stale:
            return doc
        for reservation in stale:
            removed = CalibrationSessionService.finalize_child(
                project_id=doc.project_id,
                calibration_session_id=doc.calibration_session_id,
                reservation_id=reservation.reservation_id,
            )
            if removed:
                _reject_unlaunched_run(reservation)
        return CalibrationSessionService._load(doc.project_id, doc.calibration_session_id)

    def _blockers(self, doc: CalibrationSessionDocument) -> CloseBlockers:
        """What still runs, waits, or is being started, read from every child of the session.

        Never limited to the children a detail response lists. Each agent session is loaded
        as everywhere else (half-written records finished, expiry applied), and one that has
        ended still blocks while an operation it passed the gate for has not settled.
        """
        found = CloseBlockers()
        for reservation in doc.pending_children:
            if not _reservation_stale(reservation):
                found.blockers.append(f"{_child_label(reservation)} is being started")
            elif (
                reservation.kind == CalibrationChildKind.AGENT_SESSION
                and AgentSessionDocument.find_one(
                    {"project_id": doc.project_id, "session_id": reservation.child_id}
                ).run()
                is None
            ):
                found.unknown_starts.append(reservation)
            # An older reservation whose child exists is decided by the child below.
        scope = {"project_id": doc.project_id, "calibration_session_id": doc.calibration_session_id}
        runs = CalibrationPipelineRunDocument.find(
            {
                **scope,
                **LISTED_RUNS,
                "status": {"$ne": CalibrationPipelineRunStatus.REJECTED.value},
            }
        ).sort([("requested_at", SortDirection.ASCENDING)])
        for run in runs.run():
            blocker, unknown = _run_blocker(self._run_response(run))
            if blocker:
                found.blockers.append(blocker)
            if unknown:
                found.unknown_runs.append(unknown)
        agents = AgentSessionDocument.find(scope).sort([("created_at", SortDirection.ASCENDING)])
        for listed in agents.run():
            agent = load_agent_session(doc.project_id, listed.session_id)
            if agent.calibration_admission in UNADMITTED_ADMISSIONS:
                # Never admitted, so nothing ran in it. A pending one's reservation is still
                # here: a recent one blocks above as being started, and a close clears an
                # older one, which rejects the session.
                continue
            status_now = effective_session_status(agent.status, agent.expires_at)
            if status_now == AgentSessionStatus.WAITING_FOR_HUMAN:
                found.blockers.append(f"agent session {agent.session_id} waits for a person")
                continue
            if status_now in OPEN_AGENT_STATUSES:
                found.blockers.append(f"agent session {agent.session_id} is active")
                continue
            found.blockers.extend(
                f"agent session {agent.session_id} {op['kind'].replace('_', ' ')} "
                f"{op['id']} is {op['status']}"
                for op in in_flight_operations(doc.project_id, agent.session_id)
            )
        return found

    @staticmethod
    def _recent_runs(doc: CalibrationSessionDocument) -> list[CalibrationPipelineRunDocument]:
        runs: list[CalibrationPipelineRunDocument] = (
            CalibrationPipelineRunDocument.find(
                {
                    "project_id": doc.project_id,
                    "calibration_session_id": doc.calibration_session_id,
                    **LISTED_RUNS,
                }
            )
            .sort([("requested_at", SortDirection.DESCENDING)])
            .limit(MAX_DETAIL_CHILDREN)
            .run()
        )
        return list(reversed(runs))

    def _run_response(self, run: CalibrationPipelineRunDocument) -> CalibrationPipelineRunResponse:
        # Every step of the run on its chip: those stamped with the run, or, for a run recorded
        # before the stamp existed, those of its flow run.
        executions: list[ExecutionHistoryDocument] = (
            ExecutionHistoryDocument.find(execution_scope_of_run(run))
            .sort(
                [
                    ("start_at", SortDirection.ASCENDING),
                    ("execution_id", SortDirection.ASCENDING),
                ]
            )
            .run()
        )
        pipeline = None
        if executions and self._executions is not None:
            pipeline = self._executions.pipeline_progress_of(run.project_id, executions)
        return CalibrationPipelineRunResponse(
            run_id=run.run_id,
            # Only runs of a session are listed here, so every one has it.
            calibration_session_id=run.calibration_session_id or "",
            chip_id=run.chip_id,
            run_kind=run.run_kind,
            trigger=run.trigger,
            run_name=run.run_name or run.pipeline_name,
            agent_session_id=run.agent_session_id,
            action_id=run.action_id,
            idempotency_key=run.idempotency_key,
            requested_by=run.requested_by,
            reported_origin=run.reported_origin,
            dispatch_status=dispatch_status(run),
            attempts=run.attempts,
            pipeline_name=run.pipeline_name,
            backend_name=run.backend_name,
            flow_run_id=run.flow_run_id,
            flow_end_state=run.flow_end_state,
            execution_id=run.execution_id,
            error=run.error,
            requested_at=run.requested_at,
            updated_at=run.updated_at,
            pipeline=pipeline,
            executions=[execution_summary(execution) for execution in executions],
        )

    @staticmethod
    def _agent_children(doc: CalibrationSessionDocument) -> list[CalibrationAgentSessionChild]:
        sessions: list[AgentSessionDocument] = (
            AgentSessionDocument.find(
                {
                    "project_id": doc.project_id,
                    "calibration_session_id": doc.calibration_session_id,
                }
            )
            .sort([("created_at", SortDirection.DESCENDING)])
            .limit(MAX_DETAIL_CHILDREN)
            .run()
        )
        sessions.reverse()
        if not sessions:
            return []
        # The executions each session's actions dispatched, as the agent session resolver
        # links them everywhere else.
        links = resolve_chip_links(doc.project_id, doc.chip_id)
        wanted = sorted(
            {
                link.execution_id
                for session in sessions
                for link in links.by_session.get(session.session_id, [])
            }
        )
        executions = {
            execution.execution_id: execution
            for execution in ExecutionHistoryDocument.find(
                {
                    "project_id": doc.project_id,
                    "chip_id": doc.chip_id,
                    "execution_id": {"$in": wanted},
                }
            ).run()
        }
        children: list[CalibrationAgentSessionChild] = []
        for session in sessions:
            linked = [
                executions[link.execution_id]
                for link in links.by_session.get(session.session_id, [])
                if link.execution_id in executions
            ]
            children.append(
                CalibrationAgentSessionChild(
                    session_id=session.session_id,
                    status=effective_session_status(session.status, session.expires_at),
                    created_by=session.created_by,
                    created_at=session.created_at,
                    expires_at=session.expires_at,
                    autonomy=session.policy.autonomy,
                    qids=list(session.policy.qids),
                    allowed_tasks=list(session.policy.allowed_tasks),
                    action_count=session.action_count,
                    active_intervention_id=session.active_intervention_id,
                    model_name=model_label(session.model),
                    calibration_admission=session.calibration_admission,
                    executions=[execution_summary(execution) for execution in linked],
                )
            )
        return children


@dataclass
class CloseBlockers:
    """What a close must wait for, and what it may only pass with an acknowledgment."""

    blockers: list[str] = field(default_factory=list)
    unknown_runs: list[str] = field(default_factory=list)
    unknown_starts: list[CalibrationChildReservation] = field(default_factory=list)


def _reservation_bson(reservation: CalibrationChildReservation) -> dict[str, Any]:
    return {
        "reservation_id": reservation.reservation_id,
        "kind": reservation.kind.value,
        "child_id": reservation.child_id,
        "reserved_by": reservation.reserved_by,
        "reserved_at": reservation.reserved_at,
    }


def _reject_unlaunched_run(reservation: CalibrationChildReservation) -> None:
    """Mark the run of a pipeline reservation that never launched as rejected.

    Matches only the attempt that holds this reservation and is still ``dispatching``, so a
    run another attempt holds, or one already settled, is left alone.
    """
    if reservation.kind != CalibrationChildKind.PIPELINE_RUN:
        return
    try:
        CalibrationPipelineRunDocument.get_motor_collection().update_one(
            {
                "run_id": reservation.child_id,
                "reservation_id": reservation.reservation_id,
                "status": CalibrationPipelineRunStatus.DISPATCHING.value,
            },
            {
                "$set": {
                    "status": CalibrationPipelineRunStatus.REJECTED.value,
                    "error": "The run was not launched: its request stopped, or the "
                    "calibration session was closed, before the launch",
                    "updated_at": now(),
                }
            },
        )
    except Exception:
        # It stays dispatching, which a read reports as unknown once stale.
        logger.exception("Failed to record pipeline run %s as not launched", reservation.child_id)


def _reject_unadmitted_agent(
    project_id: str, reservation: CalibrationChildReservation, *, actor: str
) -> None:
    """Reject the agent session of a reservation a close cleared, if it was written.

    Its admission can no longer be finalized. A failure here changes nothing: the session
    stays ``pending``, which refuses every operation, and its next load rejects it.
    """
    try:
        agent = AgentSessionDocument.find_one(
            {
                "project_id": project_id,
                "session_id": reservation.child_id,
                "calibration_reservation_id": reservation.reservation_id,
            }
        ).run()
        if agent is not None:
            reject_calibration_child(agent, actor=actor)
    except Exception:
        logger.exception("Failed to reject agent session %s", reservation.child_id)


def _run_blocker(run: CalibrationPipelineRunResponse) -> tuple[str | None, str | None]:
    """Whether one pipeline run blocks a close, or has an unknown dispatch outcome."""
    state = run.dispatch_status
    if state == CalibrationPipelineRunStatus.DISPATCHING:
        return f"pipeline run {run.run_id} is being dispatched", None
    if state == CalibrationPipelineRunStatus.UNKNOWN:
        return None, run.run_id
    if state != CalibrationPipelineRunStatus.DISPATCHED:
        return None, None
    if run.pipeline is not None:
        open_run = run.pipeline.status in OPEN_EXECUTION_STATUSES
    elif run.executions:
        open_run = any(e.status in OPEN_EXECUTION_STATUSES for e in run.executions)
    elif now() - (utc(run.updated_at) or now()) > DISPATCH_STALE_AFTER:
        # Launched long ago and no execution of it was ever recorded: whether it runs is
        # unknown, not known to be running.
        return None, run.run_id
    else:
        # Launched moments ago; its first execution is not recorded yet.
        open_run = True
    return (f"pipeline run {run.run_id} is running" if open_run else None), None
