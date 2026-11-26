"""Launch runs at most once per idempotency key, whether or not they join a calibration session.

A run (``RunDocument``) is recorded before its flow run is created and owns everything that
makes the launch safe: the request hash a retry must repeat, the idempotency scope a retry is
found by, the dispatch token of the attempt that holds the launch, the attempt's admission, the
dispatch outcome, and the response a retry gets back. A calibration session is an optional
association: a request that names one is checked and reserved in it before anything starts,
and a request that names none gets an automatic one. Neither the
session's existence nor its state is read to decide whether a recorded run may be replayed,
retried, or carried out.

A launch with a session is four writes: a reservation pushed into the open session (the
session's admission control), the run (``admission`` ``pending``), the removal of the
reservation by the same request (``finalize``), and the run's ``admission`` ``admitted``. Only
then is the flow run created. A run recorded without a session (an action of an agent session
that has none) is written already admitted.
A close of the session between these writes either refuses the run before it launches or, once
it was admitted, leaves it alone: closing a session stops new runs from joining it and never
invalidates one already admitted.

Retries: a dispatched run returns its recorded response; a run still dispatching, or one whose
outcome is unknown, is refused rather than launched again; only a run QDash refused before
creating a flow run (``rejected``) is launched again, in the same session it was recorded in.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from qdash.api.services.agent_execution_links import utc
from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import CalibrationChildKind
from qdash.datamodel.run import (
    RunAdmission,
    RunAssociation,
    RunDispatchStatus,
    RunIdentity,
    RunKind,
    RunTrigger,
)
from qdash.dbmodel.run import RUN_DISPATCH_STALE_AFTER, RunDocument
from qdash.repository.calibration_run import (
    automatic_objective,
    automatic_session_id_for_key,
    insert_or_load_automatic_session,
)
from qdash.repository.run_ledger import (
    RunMismatch,
    RunScopeIndexConflict,
    agent_action_scope,
    insert_run,
    key_scope,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from qdash.api.schemas.flow import ExecuteFlowResponse
    from qdash.api.services.calibration_session_service import CalibrationSessionService
    from qdash.datamodel.launch_origin import ReportedLaunchOrigin
    from qdash.dbmodel.calibration_session import CalibrationSessionDocument

logger = logging.getLogger("uvicorn.app")

# A launch reports back within seconds; one still dispatching after this may have died
# between creating the flow run and recording it, so its outcome is unknown.
DISPATCH_STALE_AFTER = RUN_DISPATCH_STALE_AFTER
# Launch failures raised before any flow run exists: the hardware is busy (409) or the
# worker has not registered the deployment (503).
DEFINITE_REFUSALS = frozenset({status.HTTP_409_CONFLICT, status.HTTP_503_SERVICE_UNAVAILABLE})


@dataclass(frozen=True)
class RunDispatch:
    """What a run launch returned: the stored response, the run, and its session if any."""

    response: dict[str, Any]
    run_id: str
    replayed: bool
    calibration_session_id: str | None = None


# Earlier name, kept for callers that still use it.
PipelineDispatch = RunDispatch


def run_request_hash(kind: RunKind, chip_id: str, request: dict[str, Any]) -> str:
    """Hash of what a retry of a workflow or task run must repeat to reuse its key."""
    payload = json.dumps(
        {"run_kind": kind.value, "chip_id": chip_id, "request": request},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def pipeline_request_hash(
    chip_id: str,
    spec: dict[str, Any],
    backend_name: str | None,
    decision_id: str | None = None,
) -> str:
    """Hash of what a retry must repeat to reuse a pipeline run's idempotency key.

    ``decision_id`` enters the hash only when given, so a request without one hashes as it
    always did.
    """
    fields: dict[str, Any] = {"chip_id": chip_id, "spec": spec, "backend_name": backend_name}
    if decision_id is not None:
        fields["decision_id"] = decision_id
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _run_name(run_name: str | Callable[[Any], str], validated: Any) -> str:
    """The run's display name, derived from the validated request when given as a function."""
    return run_name(validated) if callable(run_name) else run_name


@dataclass(frozen=True)
class RecordedPlan:
    """The stored plan a run carries out, recorded on the run for its audit."""

    plan_id: str
    review_digest: str
    review: dict[str, Any]


def plan_request_hash(
    plan_id: str,
    expected_review_digest: str,
    chip_id: str,
    backend_name: str | None,
    decision_id: str | None = None,
) -> str:
    """Hash of what a retry of a stored plan's run must repeat to reuse its idempotency key.

    It is derived from the request alone, never from the stored plan, so a retry of a run
    already dispatched is answered after the plan expired or was deleted. The ``request``
    namespace keeps it apart from every spec request's hash.
    """
    fields: dict[str, Any] = {
        "request": "calibration_pipeline_plan_execute/v1",
        "plan_id": plan_id,
        "expected_review_digest": expected_review_digest,
        "chip_id": chip_id,
        "backend_name": backend_name,
    }
    if decision_id is not None:
        fields["decision_id"] = decision_id
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def scoped_request_hash(request_hash: str, calibration_session_id: str | None) -> str:
    """The hash a run recorded with a scope stores: the request and the session it named.

    A request that names no session hashes as the request alone, so its retry matches the
    automatic session the first attempt was given, or none for a run recorded without one. A
    request that names one also hashes that session, so the same key with another session, or
    without one, is a different request.
    """
    if calibration_session_id is None:
        return request_hash
    return hashlib.sha256(
        f"{request_hash}\x1fcalibration_session:{calibration_session_id}".encode()
    ).hexdigest()


def _stale(doc: RunDocument) -> bool:
    updated = utc(doc.updated_at)
    return updated is not None and now() - updated > DISPATCH_STALE_AFTER


def dispatch_status(doc: RunDocument) -> RunDispatchStatus:
    """The run's dispatch state as a read sees it: a stale ``dispatching`` is ``unknown``."""
    if doc.status == RunDispatchStatus.DISPATCHING and _stale(doc):
        return RunDispatchStatus.UNKNOWN
    return doc.status


@dataclass(frozen=True)
class _Found:
    run: RunDocument
    # Found by its original scope (session and key): recorded before runs had a scope.
    legacy: bool


class RunLedger:
    """Record, launch, replay, and settle runs; associate them with calibration sessions."""

    def __init__(self, sessions: CalibrationSessionService) -> None:
        self._sessions = sessions

    async def launch(
        self,
        *,
        project_id: str,
        username: str,
        chip_id: str,
        kind: RunKind,
        run_name: str | Callable[[Any], str],
        request_hash: str,
        calibration_session_id: str | None,
        idempotency_key: str | None,
        validate: Callable[[], Any],
        dispatch: Callable[[Any, RunIdentity], Awaitable[ExecuteFlowResponse]],
        response: Callable[[Any, ExecuteFlowResponse], dict[str, Any]],
        recorded_spec: Callable[[Any], dict[str, Any] | None] | None = None,
        backend_name: str | None = None,
        reported_origin: ReportedLaunchOrigin | None = None,
        decision_id: str | None = None,
        preflight: Callable[[Any], None] | None = None,
        async_preflight: Callable[[Any], Awaitable[None]] | None = None,
        session_name: str | None = None,
        recorded_plan: Callable[[Any], RecordedPlan | None] | None = None,
    ) -> RunDispatch:
        """Launch one run at most once per idempotency key.

        ``run_name`` may be a function of the validated request, called only once the request
        was validated, so a replayed run never needs what the name is derived from.

        ``recorded_plan`` returns, for a run started from a stored calibration pipeline plan,
        the plan's provenance, recorded on the run with the spec.

        ``session_name`` is the name (objective) of the automatic session a run without
        ``calibration_session_id`` creates, instead of the default named after the run; it is
        applied before the session is created and never renames an existing session.

        A retry with the same key is found by the run's own scope (the signed-in user and the
        key), wherever the run was grouped, and gets the recorded answer. Otherwise the run is
        new: with ``calibration_session_id`` it joins that session, which must be the
        signed-in user's, open, and on the run's chip, or the request is refused before
        anything is recorded or launched. Without one it joins an automatic session. Without a
        key, every request is a new run, as an unkeyed request always was a new launch.

        The request is validated, and then given to ``preflight`` (which refuses, for example,
        a run whose hardware is already in use) and then ``async_preflight`` (which refuses, for
        example, a deployment that cannot run it), before an automatic session is created or the
        run is recorded or reserved, so a refused request leaves nothing behind. A retry that
        gets its recorded answer is neither validated nor checked again.
        """
        key = idempotency_key or f"srv-{uuid4()}"
        hashed = scoped_request_hash(request_hash, calibration_session_id)
        found = self._find(project_id, username, key, calibration_session_id)
        if found is not None:
            replay = self._replay(found.run, request_hash if found.legacy else hashed)
            if replay is not None:
                return replay
            validated = await self._validated(validate, preflight, async_preflight)
            name = _run_name(run_name, validated)
            self._check_decision(
                project_id, found.run.calibration_session_id, decision_id, validated
            )
            return await self._attempt(
                existing=found.run,
                project_id=project_id,
                calibration_session_id=found.run.calibration_session_id,
                association=found.run.association,
                username=username,
                idempotency_key=key,
                request_hash=found.run.request_hash,
                chip_id=chip_id,
                kind=kind,
                run_name=name,
                validated=validated,
                dispatch=dispatch,
                response=response,
                recorded_spec=recorded_spec,
                recorded_plan=recorded_plan,
                backend_name=backend_name,
                reported_origin=reported_origin,
                decision_id=decision_id,
            )

        session: CalibrationSessionDocument
        if calibration_session_id is not None:
            # Checked before anything is validated or recorded: a session that does not exist,
            # is another user's, or is on another chip refuses the request here, and one that
            # is closed refuses it when the run is reserved. Never a run without the session.
            session = self._sessions.owned(project_id, calibration_session_id, username)
            if session.chip_id != chip_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        f"Calibration session {calibration_session_id} is on chip "
                        f"{session.chip_id}, not {chip_id}"
                    ),
                )
            association = RunAssociation.EXPLICIT
            validated = await self._validated(validate, preflight, async_preflight)
            name = _run_name(run_name, validated)
        else:
            validated = await self._validated(validate, preflight, async_preflight)
            name = _run_name(run_name, validated)
            try:
                session = insert_or_load_automatic_session(
                    calibration_session_id=automatic_session_id_for_key(project_id, username, key),
                    project_id=project_id,
                    chip_id=chip_id,
                    username=username,
                    objective=session_name or automatic_objective(kind, name),
                )
            except RunMismatch as exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            association = RunAssociation.AUTOMATIC
        session_id = session.calibration_session_id
        self._check_decision(project_id, session_id, decision_id, validated, session=session)
        return await self._attempt(
            existing=None,
            project_id=project_id,
            calibration_session_id=session_id,
            association=association,
            username=username,
            idempotency_key=key,
            request_hash=hashed,
            chip_id=chip_id,
            kind=kind,
            run_name=name,
            validated=validated,
            dispatch=dispatch,
            response=response,
            recorded_spec=recorded_spec,
            recorded_plan=recorded_plan,
            backend_name=backend_name,
            reported_origin=reported_origin,
            decision_id=decision_id,
        )

    @staticmethod
    async def _validated(
        validate: Callable[[], Any],
        preflight: Callable[[Any], None] | None,
        async_preflight: Callable[[Any], Awaitable[None]] | None,
    ) -> Any:
        """The validated request, refused when one of its preflight checks fails."""
        validated = validate()
        if preflight is not None:
            preflight(validated)
        if async_preflight is not None:
            await async_preflight(validated)
        return validated

    # -- Agent actions -------------------------------------------------------------------

    @staticmethod
    def begin_agent_action_run(
        *,
        project_id: str,
        calibration_session_id: str | None,
        chip_id: str,
        agent_session_id: str,
        action_id: str,
        requested_by: str,
        run_name: str,
    ) -> tuple[RunDocument, RunIdentity]:
        """Record the run of an agent action's dispatch, admitted by its agent session.

        The agent session is the authority: its policy, gates, and dispatch reservation
        admitted the action, which is dispatched at most once. The run records that launch,
        in the calibration session the agent session was admitted to (which cannot close
        while the agent session is active) or in none, so it needs no reservation of its own.
        It is keyed by the action, so a second attempt to record it finds the first.
        """
        run_id = f"cpr-action-{action_id}"
        timestamp = now()
        doc = RunDocument(
            run_id=run_id,
            project_id=project_id,
            calibration_session_id=calibration_session_id,
            association=(
                RunAssociation.AGENT_SESSION
                if calibration_session_id is not None
                else RunAssociation.NONE
            ),
            chip_id=chip_id,
            run_kind=RunKind.AGENT_ACTION,
            trigger=RunTrigger.API,
            run_name=run_name,
            agent_session_id=agent_session_id,
            action_id=action_id,
            idempotency_key=agent_action_scope(action_id),
            idempotency_scope=agent_action_scope(action_id),
            request_hash="",
            requested_by=requested_by,
            dispatch_token=str(uuid4()),
            admission=RunAdmission.ADMITTED,
            requested_at=timestamp,
            updated_at=timestamp,
        )
        try:
            insert_run(doc)
        except DuplicateKeyError:
            found = RunDocument.find_one({"project_id": project_id, "run_id": run_id}).run()
            if (
                found is None
                or found.calibration_session_id != calibration_session_id
                or found.agent_session_id != agent_session_id
            ):
                raise
            doc = found
        return doc, RunIdentity(
            calibration_session_id=calibration_session_id,
            run_id=run_id,
            dispatch_token=doc.dispatch_token,
        )

    @classmethod
    def settle_agent_action_run(
        cls,
        claim: RunDocument,
        *,
        dispatched: ExecuteFlowResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Record how an agent action's launch ended, with the same rules as any run."""
        if dispatched is not None:
            execution_id = dispatched.execution_id
            cls.settle(
                claim,
                RunDispatchStatus.DISPATCHED,
                flow_run_id=dispatched.flow_run_id,
                execution_id=execution_id if execution_id != dispatched.flow_run_id else None,
            )
            return
        definite = isinstance(error, HTTPException) and error.status_code in DEFINITE_REFUSALS
        cls.settle(
            claim,
            RunDispatchStatus.REJECTED if definite else RunDispatchStatus.UNKNOWN,
            error=str(getattr(error, "detail", None) or type(error).__name__),
        )

    # -- Internals -----------------------------------------------------------------------

    def _find(
        self,
        project_id: str,
        username: str,
        idempotency_key: str,
        calibration_session_id: str | None,
    ) -> _Found | None:
        """The run a retry of this key reaches, by its scope or, if older, its original scope.

        A run recorded before scopes existed was keyed by its session and the key: the named
        session, or the automatic session derived from the user and the key. Those runs keep
        that scope; a request that reaches neither starts a new run, as it did then.
        """
        scoped = RunDocument.find_one(
            {"project_id": project_id, "idempotency_scope": key_scope(username, idempotency_key)}
        ).run()
        if scoped is not None:
            return self._recovered(scoped, legacy=False)
        legacy_session = calibration_session_id or automatic_session_id_for_key(
            project_id, username, idempotency_key
        )
        legacy = RunDocument.find_one(
            {
                "project_id": project_id,
                "calibration_session_id": legacy_session,
                "idempotency_key": idempotency_key,
                "idempotency_scope": None,
            }
        ).run()
        if legacy is None:
            return None
        if legacy.requested_by != username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Run {legacy.run_id} was requested by another user",
            )
        return self._recovered(legacy, legacy=True)

    def _recovered(self, run: RunDocument, *, legacy: bool) -> _Found:
        """The run after rejecting an attempt whose request stopped before launching it.

        Only an attempt still holding a reservation in its session can be such an attempt;
        rejecting it lets the same key launch the run again.
        """
        if (
            run.status == RunDispatchStatus.DISPATCHING
            and run.reservation_id is not None
            and run.calibration_session_id is not None
        ):
            self._sessions.recover_reservations(run.project_id, run.calibration_session_id)
            fresh = RunDocument.find_one({"project_id": run.project_id, "run_id": run.run_id}).run()
            if fresh is not None:
                run = fresh
        return _Found(run=run, legacy=legacy)

    def _check_decision(
        self,
        project_id: str,
        calibration_session_id: str | None,
        decision_id: str | None,
        validated: Any,
        *,
        session: CalibrationSessionDocument | None = None,
    ) -> None:
        if decision_id is None:
            return
        if calibration_session_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "decision_id names a decision of a calibration session, but this run "
                    "joins none. Pass the decision's calibration_session_id."
                ),
            )
        # Imported here: the audit reads agent sessions, whose service imports this module.
        from qdash.api.services.calibration_session_audit import check_run_decision

        check_run_decision(
            session or self._sessions.load(project_id, calibration_session_id),
            decision_id,
            getattr(validated, "targets", None),
            getattr(validated, "spec", None),
        )

    async def _attempt(
        self,
        *,
        existing: RunDocument | None,
        project_id: str,
        calibration_session_id: str | None,
        association: RunAssociation | None,
        username: str,
        idempotency_key: str,
        request_hash: str,
        chip_id: str,
        kind: RunKind,
        run_name: str,
        validated: Any,
        dispatch: Callable[[Any, RunIdentity], Awaitable[ExecuteFlowResponse]],
        response: Callable[[Any, ExecuteFlowResponse], dict[str, Any]],
        recorded_spec: Callable[[Any], dict[str, Any] | None] | None,
        backend_name: str | None,
        reported_origin: ReportedLaunchOrigin | None,
        decision_id: str | None,
        recorded_plan: Callable[[Any], RecordedPlan | None] | None = None,
    ) -> RunDispatch:
        """Record, admit, launch, and settle one attempt of a new or refused run."""
        run_id = existing.run_id if existing is not None else f"cpr-{uuid4()}"
        reservation = None
        if calibration_session_id is not None:
            reservation = self._sessions.reserve_child(
                project_id=project_id,
                calibration_session_id=calibration_session_id,
                chip_id=chip_id,
                username=username,
                kind=CalibrationChildKind.PIPELINE_RUN,
                child_id=run_id,
            )
        try:
            claim = self._claim(
                existing=existing,
                run_id=run_id,
                reservation_id=reservation.reservation_id if reservation is not None else None,
                project_id=project_id,
                calibration_session_id=calibration_session_id,
                association=association,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                chip_id=chip_id,
                username=username,
                kind=kind,
                run_name=run_name,
                reported_origin=reported_origin,
                spec=recorded_spec(validated) if recorded_spec is not None else None,
                decision_id=decision_id,
                plan=recorded_plan(validated) if recorded_plan is not None else None,
            )
            # Only an attempt that removes its own reservation may launch: a close that
            # cleared it meanwhile has already counted this run as never started.
            finalized = reservation is None or self._sessions.finalize_child(
                project_id=project_id,
                calibration_session_id=str(calibration_session_id),
                reservation_id=reservation.reservation_id,
            )
        except BaseException:
            if reservation is not None:
                # Nothing was launched for this reservation, and nothing will be.
                self._sessions.release_child(
                    project_id=project_id,
                    calibration_session_id=str(calibration_session_id),
                    reservation_id=reservation.reservation_id,
                )
                self._sessions.reject_unlaunched(reservation)
            raise
        if reservation is not None:
            if not finalized:
                self._sessions.reject_unlaunched(reservation)
                raise self._sessions.closed(str(calibration_session_id))
            self._admit(claim)

        identity = RunIdentity(
            calibration_session_id=calibration_session_id,
            run_id=claim.run_id,
            dispatch_token=claim.dispatch_token,
        )
        try:
            dispatched = await dispatch(validated, identity)
        except HTTPException as exc:
            definite = exc.status_code in DEFINITE_REFUSALS
            self.settle(
                claim,
                RunDispatchStatus.REJECTED if definite else RunDispatchStatus.UNKNOWN,
                error=str(exc.detail),
            )
            if definite:
                raise
            where = (
                f" of calibration session {calibration_session_id}"
                if calibration_session_id
                else ""
            )
            raise HTTPException(
                status_code=exc.status_code,
                detail=(
                    f"{exc.detail}. The run may have started anyway: run {claim.run_id}{where} "
                    "is recorded with an unknown outcome and is not launched again with this "
                    "key. Check the Execution list before starting another."
                ),
            ) from exc
        except BaseException as exc:
            self.settle(claim, RunDispatchStatus.UNKNOWN, error=type(exc).__name__)
            raise

        stored = response(validated, dispatched)
        execution_id = dispatched.execution_id
        self.settle(
            claim,
            RunDispatchStatus.DISPATCHED,
            flow_run_id=dispatched.flow_run_id,
            # The response falls back to the flow run ID when no execution was pre-created.
            execution_id=execution_id if execution_id != dispatched.flow_run_id else None,
            response=stored,
            backend_name=str(getattr(validated, "backend_name", None) or backend_name or ""),
        )
        return RunDispatch(
            response=stored,
            run_id=claim.run_id,
            replayed=False,
            calibration_session_id=calibration_session_id,
        )

    @staticmethod
    def _replay(existing: RunDocument, request_hash: str) -> RunDispatch | None:
        """The recorded answer to a retry, a refusal, or None when the run may launch again."""
        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Idempotency key {existing.idempotency_key} was used for a different "
                    f"request (run {existing.run_id})"
                ),
            )
        state = dispatch_status(existing)
        if state == RunDispatchStatus.DISPATCHED and existing.response is not None:
            return RunDispatch(
                response=existing.response,
                run_id=existing.run_id,
                replayed=True,
                calibration_session_id=existing.calibration_session_id,
            )
        if state == RunDispatchStatus.REJECTED:
            return None
        if state == RunDispatchStatus.DISPATCHING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Run {existing.run_id} is still being dispatched",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"The dispatch outcome of run {existing.run_id} is unknown; it may "
                "be running. It is not launched again with this key. Check the Execution "
                "list before starting another run."
            ),
        )

    @staticmethod
    def _claim(
        *,
        existing: RunDocument | None,
        run_id: str,
        reservation_id: str | None,
        project_id: str,
        calibration_session_id: str | None,
        association: RunAssociation | None,
        idempotency_key: str,
        request_hash: str,
        chip_id: str,
        username: str,
        kind: RunKind,
        run_name: str,
        reported_origin: ReportedLaunchOrigin | None = None,
        spec: dict[str, Any] | None = None,
        decision_id: str | None = None,
        plan: RecordedPlan | None = None,
    ) -> RunDocument:
        """Record the launch before it happens: a new run, or a new attempt of a refused one.

        The attempt is ``pending`` admission while it holds a reservation, and ``admitted``
        at once without one.
        """
        token = str(uuid4())
        timestamp = now()
        admission = RunAdmission.PENDING if reservation_id is not None else RunAdmission.ADMITTED
        provenance: dict[str, Any] = (
            {
                "plan_id": plan.plan_id,
                "review_digest": plan.review_digest,
                "approved_plan": plan.review,
            }
            if plan is not None
            else {}
        )
        if existing is None:
            doc = RunDocument(
                run_id=run_id,
                reservation_id=reservation_id,
                admission=admission,
                project_id=project_id,
                calibration_session_id=calibration_session_id,
                association=association,
                chip_id=chip_id,
                run_kind=kind,
                run_name=run_name,
                idempotency_key=idempotency_key,
                idempotency_scope=key_scope(username, idempotency_key),
                request_hash=request_hash,
                requested_by=username,
                reported_origin=reported_origin,
                dispatch_token=token,
                pipeline_name=run_name if kind == RunKind.PIPELINE else "",
                spec=spec,
                decision_id=decision_id,
                requested_at=timestamp,
                updated_at=timestamp,
                **provenance,
            )
            try:
                insert_run(doc)
            except RunScopeIndexConflict as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
                ) from exc
            except DuplicateKeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Another request with this idempotency key is being dispatched",
                ) from exc
            return doc
        result = RunDocument.get_motor_collection().update_one(
            {
                "run_id": existing.run_id,
                "status": RunDispatchStatus.REJECTED.value,
                "dispatch_token": existing.dispatch_token,
            },
            {
                "$set": {
                    "status": RunDispatchStatus.DISPATCHING.value,
                    "dispatch_token": token,
                    "reservation_id": reservation_id,
                    "admission": admission.value,
                    "error": "",
                    "spec": spec,
                    **provenance,
                    "updated_at": timestamp,
                },
                "$inc": {"attempts": 1},
            },
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another request with this idempotency key is being dispatched",
            )
        claimed: RunDocument = existing.model_copy(
            update={
                "status": RunDispatchStatus.DISPATCHING,
                "dispatch_token": token,
                "reservation_id": reservation_id,
                "admission": admission,
                "attempts": existing.attempts + 1,
                "error": "",
                "spec": spec,
                **provenance,
            }
        )
        return claimed

    @classmethod
    def _admit(cls, claim: RunDocument) -> None:
        """Record on the run that its attempt was admitted to its session, before the launch.

        The reservation was finalized, so a close can no longer refuse the run; this write
        makes that admission readable from the run alone. If it cannot be written, nothing is
        launched and the attempt is recorded ``rejected``, so the same key may launch it.
        """
        try:
            result = RunDocument.get_motor_collection().update_one(
                {
                    "run_id": claim.run_id,
                    "dispatch_token": claim.dispatch_token,
                    "status": RunDispatchStatus.DISPATCHING.value,
                    "admission": RunAdmission.PENDING.value,
                },
                {"$set": {"admission": RunAdmission.ADMITTED.value, "updated_at": now()}},
            )
            admitted = result.matched_count == 1
        except Exception:
            logger.exception("Failed to record the admission of run %s", claim.run_id)
            admitted = False
        if not admitted:
            cls.settle(
                claim,
                RunDispatchStatus.REJECTED,
                error="The run's admission could not be recorded; it was not launched",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Run {claim.run_id} was not launched: its admission could not be recorded. "
                    "Retry with the same idempotency key."
                ),
            )
        claim.admission = RunAdmission.ADMITTED

    @staticmethod
    def settle(claim: RunDocument, outcome: RunDispatchStatus, **fields: Any) -> None:
        """Record the launch's outcome, only for the attempt that holds it.

        A failure to record leaves the run ``dispatching``, which a read reports as unknown
        once stale: the launch itself is never undone or repeated for it.

        The worker may have bound the run to its flow run before this settles it. A launch
        that reports another flow run than the one bound never replaces the binding: the run
        is recorded ``unknown`` instead, so neither flow run is taken for the run's.
        """
        held = {
            "run_id": claim.run_id,
            "dispatch_token": claim.dispatch_token,
            "status": RunDispatchStatus.DISPATCHING.value,
        }
        flow_run_id = fields.get("flow_run_id")
        try:
            collection = RunDocument.get_motor_collection()
            if not flow_run_id:
                collection.update_one(
                    held, {"$set": {"status": outcome.value, "updated_at": now(), **fields}}
                )
                return
            result = collection.update_one(
                {**held, "flow_run_id": {"$in": [None, flow_run_id]}},
                {"$set": {"status": outcome.value, "updated_at": now(), **fields}},
            )
            if result.matched_count == 0:
                conflict = collection.update_one(
                    held,
                    {
                        "$set": {
                            "status": RunDispatchStatus.UNKNOWN.value,
                            "updated_at": now(),
                            "error": (
                                f"The launch reported flow run {flow_run_id}, but another "
                                "flow run had already claimed this run"
                            ),
                        }
                    },
                )
                if conflict.matched_count:
                    logger.error(
                        "Run %s was claimed by another flow run than the launched %s",
                        claim.run_id,
                        flow_run_id,
                    )
        except Exception:
            logger.exception(
                "Failed to record the dispatch outcome %s of run %s",
                outcome.value,
                claim.run_id,
            )
