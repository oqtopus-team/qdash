"""Application service for policy-governed local agent sessions.

Every operation that changes hardware, backend, or calibration state honors the session's
execution barrier (``agent_session_gate``): it reserves its own record, passes a gate update
that matches only an active session, then confirms the reservation before it starts.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from bunnet import SortDirection
from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.agent_session import (
    AgentActionResponse,
    AgentCandidateCommitResponse,
    AgentCandidateResponse,
    AgentCandidateSetCommitResponse,
    AgentSessionResponse,
    ApplyAgentCandidateRequest,
    CandidateGateResponse,
    CommitAgentCandidateRequest,
    CommitAgentCandidateSetRequest,
    CreateAgentSessionRequest,
    EvaluateCandidateGateRequest,
    ExecuteAgentActionRequest,
    ListAgentActionsResponse,
    ListAgentCandidatesResponse,
    ListAgentSessionsResponse,
    StopAgentSessionRequest,
    StopAgentSessionResponse,
    SubmitAgentActionRequest,
)
from qdash.api.services.agent_intervention_service import AgentInterventionService
from qdash.api.services.agent_parameter_update import (
    BASELINE_METADATA_KEY,
    check_apply,
    check_commit,
    check_required_evaluation,
    downstream_refusal,
    paused_session_overlap,
    record_baseline,
    update_authority,
)
from qdash.api.services.agent_session_gate import (
    ADMITTED_FILTER,
    admission_refusal,
    admit_calibration_child,
    autonomous_session_refusal,
    end_notification_update,
    expire_session_if_due,
    in_flight_operations,
    load_agent_session,
    materialize_pending_action,
    materialize_pending_intervention,
    pass_execution_gate,
    raw_document,
    reject_calibration_child,
    release_abandoned_reservations,
    settle_calibration_admission,
    to_bson,
)
from qdash.api.services.agent_session_notifications import (
    AgentSessionNotificationService,
    initial_start_notification,
)
from qdash.api.services.calibration_session_service import CalibrationSessionService
from qdash.api.services.catalog_task_run import resolve_catalog_task, run_catalog_task
from qdash.api.services.run_ledger import RunLedger
from qdash.common.agent_gate import evaluate_numeric_candidate
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentAutonomy,
    AgentCandidateAcceptanceBasis,
    AgentCandidateRejection,
    AgentSessionLifecycleEvent,
    AgentSessionStatus,
    AgentSessionStopRecord,
    model_label,
)
from qdash.datamodel.calibration_session import (
    CalibrationAdmission,
    CalibrationChildKind,
    CalibrationRunKind,
)
from qdash.dbmodel.agent_parameter_state import (
    StoredParameter,
    acquire_backend_apply_lock,
    compare_and_set_parameter,
    read_parameter,
    release_backend_apply_lock,
)
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCandidateCommitDocument,
    AgentCandidateSetCommitDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.calibration_run import (
    automatic_objective,
    insert_or_load_automatic_session,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from qdash.api.schemas.task_file import TaskInfo
    from qdash.api.services.flow_service import FlowService
    from qdash.api.services.task_file_service import TaskFileService


# Most sessions one list request reads before filtering by settled status.
LIST_SESSIONS_SCAN_LIMIT = 200
# Run statuses after which a measurement no longer runs.
FINISHED_RUN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "canceled", "crashed", "skipped"}
)


def _measurement_key(
    task_name: str | None, qid: str | None, overrides: dict[str, float]
) -> tuple[str, str, tuple[tuple[str, float], ...]]:
    """Same task, target, and overrides measure the same thing."""
    return (task_name or "", qid or "", tuple(sorted(overrides.items())))


def _typed_overrides(task: TaskInfo, overrides: dict[str, float]) -> dict[str, Any]:
    """Agent overrides arrive as floats; give whole numbers to integer inputs as ints."""
    typed: dict[str, Any] = {}
    for name, value in overrides.items():
        value_type = task.input_parameters.get(name, {}).get("value_type")
        typed[name] = int(value) if value_type == "int" and float(value).is_integer() else value
    return typed


class AgentSessionService:
    """Authorize and audit actions proposed by user-operated local agents."""

    def __init__(self, intervention_service: AgentInterventionService | None = None) -> None:
        """Initialize with the service that records human interventions."""
        self._interventions = intervention_service

    @property
    def interventions(self) -> AgentInterventionService:
        """The intervention service, created on first use."""
        if self._interventions is None:
            self._interventions = AgentInterventionService()
        return self._interventions

    @property
    def notifications(self) -> AgentSessionNotificationService:
        """The session start and end messages, on the interventions' Slack channel."""
        return AgentSessionNotificationService(self.interventions.notifier)

    @staticmethod
    def _session_response(doc: AgentSessionDocument) -> AgentSessionResponse:
        return AgentSessionResponse.model_validate(
            {**doc.model_dump(), "model_name": model_label(doc.model)}
        )

    @staticmethod
    def _action_response(doc: AgentActionDocument) -> AgentActionResponse:
        return AgentActionResponse.model_validate(
            {
                **doc.model_dump(),
                "intervention_id": doc.metadata.get("intervention_id"),
                "autonomous": bool(doc.metadata.get("autonomous", False)),
                "model": doc.metadata.get("model"),
            }
        )

    @staticmethod
    def _candidate_commit_response(
        doc: AgentCandidateCommitDocument,
    ) -> AgentCandidateCommitResponse:
        return AgentCandidateCommitResponse.model_validate(doc.model_dump())

    @staticmethod
    def _candidate_set_commit_response(
        doc: AgentCandidateSetCommitDocument,
    ) -> AgentCandidateSetCommitResponse:
        return AgentCandidateSetCommitResponse.model_validate(doc.model_dump())

    @staticmethod
    def _get_action_document(
        project_id: str,
        session_id: str,
        action_id: str,
    ) -> AgentActionDocument:
        doc = AgentActionDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "action_id": action_id,
            }
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent action '{action_id}' not found",
            )
        return doc

    @staticmethod
    def _refresh_action_execution(doc: AgentActionDocument) -> AgentActionDocument:
        """Resolve a Prefect operation to its QDash execution without changing flow IDs."""
        if doc.operation_id is None:
            return doc
        # operation_id is the Prefect flow run ID. Actions dispatched before that
        # was fixed stored the QDash execution ID there instead, so match both.
        execution = ExecutionHistoryDocument.find_one(
            {
                "project_id": doc.project_id,
                "$or": [
                    {"note.flow_run_id": doc.operation_id},
                    {"execution_id": doc.operation_id},
                ],
            }
        ).run()
        if execution is None:
            return doc
        if doc.execution_id != execution.execution_id or doc.execution_status != execution.status:
            doc.execution_id = execution.execution_id
            doc.execution_status = execution.status
            # A targeted update, so it never overwrites a concurrent dispatch reservation.
            AgentActionDocument.get_motor_collection().update_one(
                {"action_id": doc.action_id},
                {
                    "$set": {
                        "execution_id": execution.execution_id,
                        "execution_status": execution.status,
                    }
                },
            )
        return doc

    @staticmethod
    def _request_hash(body: SubmitAgentActionRequest) -> str:
        # Fields at their defaults hash as they did before they existed, so a retry of an
        # older request still matches its record. The reported model is provenance, not part
        # of the proposal: a retry keeps the first record's model.
        exclude = {"model"} | {
            name
            for name, default in (("autonomous", False), ("repeat_of_action_id", None))
            if getattr(body, name) == default
        }
        payload = json.dumps(
            body.model_dump(mode="json", exclude=exclude),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _backend_apply_request_hash(body: ApplyAgentCandidateRequest) -> str:
        # A reviewed request hashes as it did before autonomous existed.
        exclude = {"autonomous"} if not body.autonomous else set()
        payload = json.dumps(
            body.model_dump(mode="json", exclude=exclude),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _candidate_commit_request_hash(
        *,
        action_id: str,
        parameter_name: str,
        body: CommitAgentCandidateRequest,
    ) -> str:
        payload = json.dumps(
            {
                "action_id": action_id,
                "parameter_name": parameter_name,
                # A reviewed request hashes as it did before autonomous commits existed.
                "body": body.model_dump(
                    mode="json",
                    exclude={"autonomous", "decision_id"} if not body.autonomous else set(),
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _candidate_set_commit_request_hash(body: CommitAgentCandidateSetRequest) -> str:
        payload = json.dumps(
            body.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _get_session_document(project_id: str, session_id: str) -> AgentSessionDocument:
        return load_agent_session(project_id, session_id)

    def create_session(
        self,
        *,
        project_id: str,
        username: str,
        body: CreateAgentSessionRequest,
    ) -> AgentSessionResponse:
        """Create an immutable authorization scope for one local agent."""
        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": body.chip_id}).run()
        if chip is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chip '{body.chip_id}' not found",
            )

        # An auto session acts without per-call approval, so it must not start work a paused
        # session of the same user is waiting on a person for.
        paused = (
            paused_session_overlap(project_id, body.chip_id, username, body.policy.qids)
            if body.policy.autonomy == AgentAutonomy.AUTO
            else None
        )
        if paused is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Your agent session {paused.session_id} on {body.chip_id} is paused for "
                    f"a person (intervention {paused.active_intervention_id}) and covers "
                    "these qubits. A new session would bypass that pause; wait for the "
                    "answer, or have the paused session stopped, first."
                ),
            )
        policy = body.policy.model_copy(
            update={
                "qids": list(dict.fromkeys(body.policy.qids)),
                "allowed_tasks": list(dict.fromkeys(body.policy.allowed_tasks)),
                "allowed_actions": list(dict.fromkeys(body.policy.allowed_actions)),
            }
        )
        session_id = str(uuid4())
        calibration = CalibrationSessionService()
        calibration_session_id = body.calibration_session_id
        if calibration_session_id is None:
            # A session started without a calibration session gets an automatic one, so the
            # runs its actions launch are recorded with a purpose like every other run. It is
            # created after the checks above, and the start is reserved and admitted in it
            # exactly as in a named one; the relation grants nothing.
            calibration_session_id = insert_or_load_automatic_session(
                calibration_session_id=f"cs-auto-{uuid4().hex}",
                project_id=project_id,
                chip_id=body.chip_id,
                username=username,
                objective=automatic_objective(
                    CalibrationRunKind.AGENT_ACTION, body.skill_name or ""
                ),
            ).calibration_session_id
        # Checked and reserved in the calibration session before the session exists; the
        # relation grants nothing, so the policy above stays the only authority.
        reservation = calibration.reserve_child(
            project_id=project_id,
            calibration_session_id=calibration_session_id,
            chip_id=body.chip_id,
            username=username,
            kind=CalibrationChildKind.AGENT_SESSION,
            child_id=session_id,
        )
        try:
            timestamp = now()
            doc = AgentSessionDocument(
                session_id=session_id,
                project_id=project_id,
                chip_id=body.chip_id,
                created_by=username,
                policy=policy,
                skill_name=body.skill_name,
                skill_version=body.skill_version,
                skill_hash=body.skill_hash,
                model=body.model,
                expires_at=timestamp + timedelta(seconds=body.expires_in_seconds),
                created_at=timestamp,
                updated_at=timestamp,
                # Stored with the session, so the start message survives a crash after insert.
                start_notification=initial_start_notification(self.notifications.enabled),
                calibration_session_id=calibration_session_id,
                # Written unadmitted: no operation passes until the reservation is finalized.
                calibration_admission=CalibrationAdmission.PENDING,
                calibration_reservation_id=reservation.reservation_id,
                records_runs=True,
            )
        except BaseException:
            calibration.release_child(
                project_id=project_id,
                calibration_session_id=calibration_session_id,
                reservation_id=reservation.reservation_id,
            )
            raise
        try:
            doc.insert()
        except DuplicateKeyError:
            # Not written: nothing can run in it.
            calibration.release_child(
                project_id=project_id,
                calibration_session_id=calibration_session_id,
                reservation_id=reservation.reservation_id,
            )
            raise
        # Any other insert failure leaves the reservation pending: whether the session was
        # written is unknown, and a close reports it until it is found or acknowledged. A
        # session written meanwhile stays unadmitted until a load decides it.
        finalized = calibration.finalize_child(
            project_id=project_id,
            calibration_session_id=calibration_session_id,
            reservation_id=reservation.reservation_id,
            admit=True,
        )
        # A crash here leaves the session pending; its next load reads the finalized
        # reservation from the calibration session and admits it, or rejects it.
        if not finalized:
            # The calibration session was closed before the start was finalized. The
            # session was never admitted, so nothing ran in it; reject and cancel it.
            reject_calibration_child(doc, actor=username)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Calibration session {calibration_session_id} was closed before "
                    f"agent session {session_id} was admitted; it was rejected and "
                    "cancelled before it could operate. Start a new calibration session."
                ),
            )
        admit_calibration_child(doc)
        return self._session_response(doc)

    def get_session(self, *, project_id: str, session_id: str) -> AgentSessionResponse:
        """Get the authoritative state for an agent session."""
        return self._session_response(self._get_session_document(project_id, session_id))

    def list_sessions(
        self,
        *,
        project_id: str,
        chip_id: str | None = None,
        created_by: str | None = None,
        statuses: list[AgentSessionStatus] | None = None,
        limit: int = 20,
    ) -> ListAgentSessionsResponse:
        """List a project's sessions, newest first, with expiry and pending pauses applied.

        Each listed session is settled the way a single read settles it, so a session past
        its expiry is reported as ``expired`` and a pause a crash left half written is
        finished before its status is filtered.
        """
        query: dict[str, Any] = {"project_id": project_id}
        if chip_id:
            query["chip_id"] = chip_id
        if created_by:
            query["created_by"] = created_by
        wanted = set(statuses or [])
        if wanted:
            stored = {status.value for status in wanted}
            if AgentSessionStatus.EXPIRED in wanted:
                # A stored active or paused session may be past its expiry.
                stored |= {
                    AgentSessionStatus.ACTIVE.value,
                    AgentSessionStatus.WAITING_FOR_HUMAN.value,
                }
            query["status"] = {"$in": sorted(stored)}
        docs = (
            AgentSessionDocument.find(query)
            .sort([("created_at", SortDirection.DESCENDING)])
            .limit(LIST_SESSIONS_SCAN_LIMIT)
            .run()
        )
        items: list[AgentSessionResponse] = []
        for doc in docs:
            settle_calibration_admission(doc)
            materialize_pending_action(doc)
            materialize_pending_intervention(doc)
            expire_session_if_due(doc)
            if wanted and doc.status not in wanted:
                continue
            items.append(self._session_response(doc))
            if len(items) >= limit:
                break
        return ListAgentSessionsResponse(items=items, total=len(items))

    def evaluate_candidate_gate(
        self,
        *,
        project_id: str,
        session_id: str,
        body: EvaluateCandidateGateRequest,
    ) -> CandidateGateResponse:
        """Evaluate a candidate against immutable session bounds without writing state."""
        session = self._get_session_document(project_id, session_id)
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        admission_refusal(session)

        bounds = session.policy.allowed_overrides.get(body.parameter_name)
        if bounds is None:
            return CandidateGateResponse(
                session_id=session_id,
                parameter_name=body.parameter_name,
                value=body.value,
                accepted=False,
                reason=f"Parameter '{body.parameter_name}' is not allowed by the session policy",
            )

        decision = evaluate_numeric_candidate(
            body.value,
            minimum=bounds.minimum,
            maximum=bounds.maximum,
        )
        return CandidateGateResponse(
            session_id=session_id,
            parameter_name=body.parameter_name,
            value=body.value,
            accepted=decision.accepted,
            reason=decision.reason,
            minimum=bounds.minimum,
            maximum=bounds.maximum,
        )

    @staticmethod
    def _policy_rejection(
        session: AgentSessionDocument,
        body: SubmitAgentActionRequest,
    ) -> str | None:
        if body.action_type not in session.policy.allowed_actions:
            return f"Action '{body.action_type.value}' is not allowed by the session policy"
        if body.action_type in (AgentActionType.REQUEST_HUMAN, AgentActionType.COMPLETE_SESSION):
            # Asking for a person or ending the session never needs measurement budget: a
            # session that used its last action can still be finished.
            return None
        if session.action_count >= session.policy.max_actions:
            return "Session action limit has been reached"
        if body.action_type != AgentActionType.RUN_TASK:
            return None
        if body.task_name not in session.policy.allowed_tasks:
            return f"Task '{body.task_name}' is not allowed by the session policy"

        disallowed_qids = sorted(set(body.qids) - set(session.policy.qids))
        if disallowed_qids:
            return f"Targets are outside the session scope: {', '.join(disallowed_qids)}"

        for name, value in body.parameter_overrides.items():
            bounds = session.policy.allowed_overrides.get(name)
            if bounds is None:
                return f"Parameter override '{name}' is not allowed"
            if not bounds.contains(value):
                return f"Parameter override '{name}' is outside the allowed bounds"
        return None

    def _session_run_tasks(self, project_id: str, session_id: str) -> list[AgentActionDocument]:
        """The session's authorized run_task actions, oldest first, with fresh run status."""
        docs = cast(
            "list[AgentActionDocument]",
            AgentActionDocument.find(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "action_type": AgentActionType.RUN_TASK.value,
                    "decision": AgentActionDecision.AUTHORIZED.value,
                },
                sort=[("created_at", SortDirection.ASCENDING)],
            ).run(),
        )
        return [self._refresh_action_execution(doc) for doc in docs]

    def _candidates_reader(
        self, project_id: str, session_id: str
    ) -> Callable[[str], list[AgentCandidateResponse]]:
        """Read an action's gated candidates; raises when its result cannot be read."""

        def read(action_id: str) -> list[AgentCandidateResponse]:
            return self.list_action_candidates(
                project_id=project_id, session_id=session_id, action_id=action_id
            ).items

        return read

    @staticmethod
    def _evaluations_of(action: AgentActionDocument) -> list[EvaluationDocument]:
        """The evaluations of an action's authoritative task result; empty when none exist."""
        if action.execution_id is None or not action.task_name or len(action.qids) != 1:
            return []
        task_result = TaskResultHistoryDocument.find_one(
            {
                "project_id": action.project_id,
                "execution_id": action.execution_id,
                "name": action.task_name,
                "qid": action.qids[0],
            },
            sort=[("end_at", SortDirection.DESCENDING)],
        ).run()
        if task_result is None:
            return []
        return cast(
            "list[EvaluationDocument]",
            EvaluationDocument.find(
                {"project_id": action.project_id, "task_id": task_result.task_id},
                sort=[("requested_at", SortDirection.ASCENDING)],
            ).run(),
        )

    def _autonomous_step_refusal(
        self,
        project_id: str,
        session: AgentSessionDocument,
        body: SubmitAgentActionRequest,
    ) -> None:
        """Refuse an autonomous run_task the session's history does not allow now.

        The caller loaded ``session`` (which writes a pending action record first) and
        authorizes only with a compare-and-set on its state version, so the history read
        here holds every action counted up to that version, and a submission that lands in
        between makes the compare-and-set fail. Dispatch progress does not change the state
        version; ``execute_action`` checks the running measurements again when it dispatches.
        """
        actions = self._session_run_tasks(project_id, session.session_id)
        qid = body.qids[0] if body.qids else None
        key = _measurement_key(body.task_name, qid, body.parameter_overrides)
        running = [
            action.action_id
            for action in actions
            if action.execution_status != "not_started"
            and action.execution_status not in FINISHED_RUN_STATUSES
        ]
        if running:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Action {', '.join(running)} of the session is still running; wait for "
                    "its result before an autonomous step"
                ),
            )
        same = [
            action
            for action in actions
            if _measurement_key(
                action.task_name,
                action.qids[0] if action.qids else None,
                action.parameter_overrides,
            )
            == key
        ]
        unstarted = [action for action in same if action.execution_status == "not_started"]
        if unstarted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Action {unstarted[0].action_id} already proposes this measurement and "
                    "was never dispatched; dispatch it instead of proposing it again"
                ),
            )
        rounds = sum(
            1 for action in actions if action.task_name == body.task_name and qid in action.qids
        )
        if rounds >= session.policy.max_rounds_per_target:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{body.task_name} on {qid} already ran {rounds} times, the session's "
                    "max_rounds_per_target"
                ),
            )
        finished = [action for action in same if action.execution_status in FINISHED_RUN_STATUSES]
        if finished and body.repeat_of_action_id not in {action.action_id for action in finished}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Action {finished[-1].action_id} already ran this exact measurement; "
                    "repeat it only with repeat_of_action_id naming a finished identical action"
                ),
            )
        if body.repeat_of_action_id is not None and not finished:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"repeat_of_action_id {body.repeat_of_action_id} is not a finished "
                    "identical measurement of this session"
                ),
            )
        if body.task_name and qid:
            waiting = downstream_refusal(
                session=session,
                actions=actions,
                task_name=body.task_name,
                qid=qid,
                candidates_of=self._candidates_reader(project_id, session.session_id),
                evaluations_of=self._evaluations_of,
            )
            if waiting:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=waiting)

    def submit_action(
        self,
        *,
        project_id: str,
        session_id: str,
        body: SubmitAgentActionRequest,
        username: str = "",
    ) -> AgentActionResponse:
        """Validate, serialize, and audit an action proposal without executing it."""
        request_hash = self._request_hash(body)
        existing = AgentActionDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "idempotency_key": body.idempotency_key,
            }
        ).run()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was already used for a different action",
                )
            return self._action_response(existing)

        session = self._get_session_document(project_id, session_id)
        # Loading the session writes the action of a request_human that crashed after it
        # paused the session, so a retry finds it here.
        recovered = AgentActionDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "idempotency_key": body.idempotency_key,
            }
        ).run()
        if recovered is not None:
            if recovered.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was already used for a different action",
                )
            return self._action_response(recovered)
        if body.autonomous:
            autonomous_session_refusal(session, username)
        if session.pending_action is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The session's previous action record is still being written; retry",
            )
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        admission_refusal(session)
        if body.expected_state_version != session.state_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Agent session state version mismatch: "
                    f"expected {body.expected_state_version}, current {session.state_version}"
                ),
            )
        if body.autonomous:
            self._autonomous_step_refusal(project_id, session, body)

        rejection = self._policy_rejection(session, body)
        decision = AgentActionDecision.REJECTED if rejection else AgentActionDecision.AUTHORIZED
        reason = rejection or "Action authorized by the session policy; execution has not started"
        next_status: AgentSessionStatus = session.status
        if decision == AgentActionDecision.AUTHORIZED:
            if body.action_type == AgentActionType.REQUEST_HUMAN:
                next_status = AgentSessionStatus.WAITING_FOR_HUMAN
            elif body.action_type == AgentActionType.COMPLETE_SESSION:
                next_status = AgentSessionStatus.COMPLETED

        timestamp = now()
        action_id = str(uuid4())
        session_update: dict[str, Any] = {"status": next_status.value, "updated_at": timestamp}
        if next_status == AgentSessionStatus.COMPLETED:
            # The end message is stored by the same update that ends the session.
            session_update |= end_notification_update(
                session,
                AgentSessionLifecycleEvent.COMPLETED,
                actor=username or session.created_by,
            )
        increments = {"state_version": 1, "action_count": 1}
        intervention = None
        if next_status == AgentSessionStatus.WAITING_FOR_HUMAN:
            # A request for a person does not use the measurement budget.
            intervention = self.interventions.build_request_human(
                session=session,
                action_id=action_id,
                username=username or session.created_by,
                diagnosis=body.diagnosis,
                model=body.model,
            )
            increments = {"state_version": 1}
        state_version_after = session.state_version + 1
        action = AgentActionDocument(
            action_id=action_id,
            session_id=session_id,
            project_id=project_id,
            idempotency_key=body.idempotency_key,
            request_hash=request_hash,
            action_type=body.action_type,
            task_name=body.task_name,
            qids=list(dict.fromkeys(body.qids)),
            parameter_overrides=body.parameter_overrides,
            diagnosis=body.diagnosis,
            decision=decision,
            reason=reason,
            state_version_before=session.state_version,
            state_version_after=state_version_after,
            created_at=timestamp,
            metadata={"intervention_id": intervention.intervention_id} if intervention else {},
        )
        if username:
            # The authenticated account that proposed the action, for the audit timeline.
            action.metadata["submitted_by"] = username
        if body.model is not None:
            # The model the client host reported for this proposal; provenance only.
            action.metadata["model"] = body.model.model_dump(mode="json")
        if body.autonomous:
            action.metadata["autonomous"] = True
            if body.repeat_of_action_id is not None:
                action.metadata["repeat_of_action_id"] = body.repeat_of_action_id
            if decision == AgentActionDecision.AUTHORIZED and (
                body.action_type == AgentActionType.RUN_TASK
            ):
                # The stored values this measurement starts from; an autonomous commit of its
                # result writes only while the stored value is still exactly this one.
                baseline = record_baseline(
                    session, body.task_name, body.qids[0] if body.qids else None
                )
                if baseline is not None:
                    action.metadata[BASELINE_METADATA_KEY] = baseline
        if intervention is not None:
            # The pause and both records are one session update; the records are written
            # from it below, or by the next load of the session after a crash.
            session_update |= self.interventions.pause_update(intervention, action=action)
        else:
            # The count and the record are one session update; the record is written from
            # it below, or by the next load of the session after a crash.
            session_update["pending_action"] = raw_document(action)
        updated = AgentSessionDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "status": AgentSessionStatus.ACTIVE.value,
                "state_version": session.state_version,
                **ADMITTED_FILTER,
                "pending_action": None,
            },
            {"$set": session_update, "$inc": increments},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent session changed while the action was being authorized",
            )
        # Loading the session writes the stored records.
        self._get_session_document(project_id, session_id)
        written = AgentActionDocument.find_one({"action_id": action_id}).run()
        if written is None:
            raise HTTPException(status_code=500, detail="Agent action record was not written")
        return self._action_response(written)

    # A stop retries its compare-and-set this often while other writes change the session.
    _STOP_ATTEMPTS = 5

    def stop_session(
        self,
        *,
        project_id: str,
        session_id: str,
        username: str,
        body: StopAgentSessionRequest,
    ) -> StopAgentSessionResponse:
        """End an active or paused session's authority on a person's request.

        One compare-and-set on the session's status and state version moves it to
        ``cancelled`` and stores who stopped it, why, and the end message, so no operation
        passes the session gate after it: no measurement is dispatched, no candidate is
        committed or applied, and no resume is claimed. An operation that passed the gate
        before the stop is not cancelled; it is reported in ``in_flight``. A session that
        already ended is left as it is (``already_ended``), and repeating a stop with its
        key returns ``already_stopped``.
        """
        session = self._get_session_document(project_id, session_id)
        outcome: str | None = None
        for _ in range(self._STOP_ATTEMPTS):
            stop = session.stop
            if stop is not None and stop.idempotency_key == body.idempotency_key:
                if stop.reason != body.reason or stop.stopped_by != username:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key was already used for a different stop",
                    )
                outcome = "already_stopped"
                break
            if session.status not in (
                AgentSessionStatus.ACTIVE,
                AgentSessionStatus.WAITING_FOR_HUMAN,
            ):
                outcome = "already_ended"
                break
            timestamp = now()
            record = AgentSessionStopRecord(
                stopped_by=username,
                stopped_at=timestamp,
                reason=body.reason,
                idempotency_key=body.idempotency_key,
                status_before=session.status,
                state_version=session.state_version + 1,
            )
            updated = AgentSessionDocument.get_motor_collection().find_one_and_update(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "status": session.status.value,
                    "state_version": session.state_version,
                },
                {
                    "$set": {
                        "status": AgentSessionStatus.CANCELLED.value,
                        "active_intervention_id": None,
                        "updated_at": timestamp,
                        "stop": to_bson(record.model_dump()),
                        # The end message is stored by the same update that ends the session.
                        **end_notification_update(
                            session, AgentSessionLifecycleEvent.CANCELLED, actor=username
                        ),
                    },
                    "$inc": {"state_version": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            if updated is not None:
                outcome = "stopped"
                break
            # Another write changed the session first; decide again on what it stored.
            session = self._get_session_document(project_id, session_id)
        if outcome is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The session kept changing while it was being stopped; send the stop again",
            )
        session = self._get_session_document(project_id, session_id)
        closed = self.interventions.close_for_stopped_session(session)
        return StopAgentSessionResponse.model_validate(
            {
                "outcome": outcome,
                "session": self._session_response(session),
                "in_flight": in_flight_operations(project_id, session_id),
                "closed_intervention_ids": closed,
            }
        )

    @staticmethod
    def _candidate_parameter(
        source_name: str,
        raw: Any,
    ) -> tuple[str, float, float, str, str] | None:
        parameter_name = source_name
        error = 0.0
        unit = ""
        value_type = "float"
        value: Any = raw

        if isinstance(raw, dict):
            parameter_name = str(raw.get("parameter_name") or source_name)
            value = raw.get("value")
            error_value = raw.get("error", 0.0)
            if isinstance(error_value, (int, float)) and not isinstance(error_value, bool):
                error = float(error_value)
            unit = str(raw.get("unit") or "")
            value_type = str(raw.get("value_type") or "float")

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            return None
        return parameter_name, numeric_value, error, unit, value_type

    @classmethod
    def gate_task_result(
        cls,
        session: AgentSessionDocument,
        action_id: str,
        task_result: TaskResultHistoryDocument,
    ) -> list[AgentCandidateResponse]:
        """Gate each numeric output of a task result against the session's immutable policy.

        The result is a function of the task result and the session policy only, so the audit
        timeline recomputes it without storing a second copy.
        """
        session_id = session.session_id
        # Only this task's gates (and legacy session-wide ones) apply to its result.
        gates = session.policy.quality_gates_for(task_result.name)
        updates = session.policy.parameter_updates
        granted = (
            set(updates.parameters)
            if updates is not None and task_result.name in updates.tasks
            else set()
        )
        items: list[AgentCandidateResponse] = []
        for source_name, raw in sorted(task_result.output_parameters.items()):
            candidate = cls._candidate_parameter(source_name, raw)
            if candidate is None:
                continue
            parameter_name, value, error, unit, value_type = candidate
            bounds = session.policy.allowed_overrides.get(parameter_name)
            basis: AgentCandidateAcceptanceBasis | None = None
            rejection: AgentCandidateRejection | None = None
            minimum = None
            maximum = None
            if bounds is None and parameter_name in granted:
                # A granted parameter without bounds: only the task's own completion checks
                # (a completed result) and the quality gates below decide.
                accepted = True
                basis = AgentCandidateAcceptanceBasis.TASK_CHECKS
                reason = "candidate passed its task's completion checks; no numeric bounds"
            elif bounds is None:
                # An output outside the session's scope, such as an incidental estimate of a
                # task whose granted output is another parameter. It says nothing about the
                # result or its other candidates.
                accepted = False
                rejection = AgentCandidateRejection.NOT_IN_SCOPE
                reason = (
                    f"Parameter '{parameter_name}' is not allowed by the session policy: not "
                    f"granted from {task_result.name} and no approved bounds. Staged for "
                    "reference only; not evidence against this result or its other candidates"
                )
            else:
                decision = evaluate_numeric_candidate(
                    value,
                    minimum=bounds.minimum,
                    maximum=bounds.maximum,
                )
                accepted = decision.accepted
                reason = decision.reason
                minimum = bounds.minimum
                maximum = bounds.maximum
                if accepted:
                    basis = AgentCandidateAcceptanceBasis.SESSION_BOUNDS
                else:
                    rejection = AgentCandidateRejection.OUTSIDE_BOUNDS

            if accepted:
                for gate in gates:
                    where = (
                        f"for task '{task_result.name}'"
                        if gate.task_name is not None
                        else "by the session-wide gate"
                    )
                    metric_value = task_result.quality_metrics.get(gate.metric_name)
                    if metric_value is None:
                        accepted = False
                        reason = f"Required quality metric '{gate.metric_name}' {where} is missing"
                        break
                    quality_decision = evaluate_numeric_candidate(
                        metric_value,
                        minimum=gate.minimum,
                        maximum=gate.maximum,
                    )
                    if not quality_decision.accepted:
                        accepted = False
                        reason = (
                            f"Quality metric '{gate.metric_name}' {where} {quality_decision.reason}"
                        )
                        break
                else:
                    if gates:
                        reason = (
                            "candidate passed deterministic bounds and quality gates"
                            if basis == AgentCandidateAcceptanceBasis.SESSION_BOUNDS
                            else "candidate passed its task's completion checks and quality "
                            "gates; no numeric bounds"
                        )
                if not accepted:
                    basis = None
                    rejection = AgentCandidateRejection.QUALITY_GATE

            items.append(
                AgentCandidateResponse(
                    session_id=session_id,
                    action_id=action_id,
                    execution_id=task_result.execution_id,
                    task_id=task_result.task_id,
                    task_name=task_result.name,
                    qid=task_result.qid,
                    source_parameter_name=source_name,
                    parameter_name=parameter_name,
                    value=value,
                    error=error,
                    unit=unit,
                    value_type=value_type,
                    quality_metrics=dict(task_result.quality_metrics),
                    applied_quality_gates=[gate.model_copy() for gate in gates],
                    acceptance_basis=basis,
                    accepted=accepted,
                    rejection=rejection,
                    reason=reason,
                    minimum=minimum,
                    maximum=maximum,
                )
            )

        return items

    def list_action_candidates(
        self,
        *,
        project_id: str,
        session_id: str,
        action_id: str,
    ) -> ListAgentCandidatesResponse:
        """Read numeric candidates from the authoritative result of one agent action."""
        session = self._get_session_document(project_id, session_id)
        action = self._get_action_document(project_id, session_id, action_id)
        if action.decision != AgentActionDecision.AUTHORIZED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidates are only available for authorized actions",
            )
        if action.action_type != AgentActionType.RUN_TASK or action.task_name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Candidates are only available for run_task actions",
            )
        if action.operation_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent action has not produced an operation",
            )
        if len(action.qids) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Candidate extraction supports exactly one target qid",
            )

        action = self._refresh_action_execution(action)
        if action.execution_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="QDash execution for the agent operation is not available yet",
            )
        task_result = TaskResultHistoryDocument.find_one(
            {
                "project_id": project_id,
                "execution_id": action.execution_id,
                "name": action.task_name,
                "qid": action.qids[0],
            },
            sort=[("end_at", SortDirection.DESCENDING)],
        ).run()
        if task_result is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Authoritative task result is not available yet",
            )
        if task_result.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Authoritative task result is not completed: {task_result.status}",
            )
        if task_result.chip_id != session.chip_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task result chip does not match the agent session",
            )

        items = self.gate_task_result(session, action_id, task_result)
        return ListAgentCandidatesResponse(items=items, total=len(items))

    @staticmethod
    def _reserve_commit(
        commit: AgentCandidateCommitDocument | AgentCandidateSetCommitDocument,
        session: AgentSessionDocument,
        request_hash: str,
        *,
        gone: str,
    ) -> AgentCandidateCommitDocument | AgentCandidateSetCommitDocument | None:
        """Reserve a commit against the session barrier before anything is persisted.

        The commit record is inserted as ``reserving`` first, so a resume check that runs
        after a later pause sees it. The session update then advances the state version only
        while the session is active, and the record is confirmed as ``committing``. Returns
        the existing record when a concurrent request with the same key won the insert.
        """
        model = type(commit)
        try:
            commit.insert()
        except DuplicateKeyError:
            existing = model.find_one(
                {
                    "project_id": commit.project_id,
                    "session_id": commit.session_id,
                    "idempotency_key": commit.idempotency_key,
                }
            ).run()
            if existing is None:
                raise
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was already used for a different candidate commit",
                ) from None
            return existing
        updated_session = AgentSessionDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": session.project_id,
                "session_id": session.session_id,
                "status": AgentSessionStatus.ACTIVE.value,
                "state_version": session.state_version,
                **ADMITTED_FILTER,
            },
            {"$set": {"updated_at": now()}, "$inc": {"state_version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if updated_session is None:
            # Nothing was persisted; the key stays free for a retry.
            model.get_motor_collection().delete_one(
                {"commit_id": commit.commit_id, "status": "reserving"}
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session changed while the {gone}",
            )
        confirmed = model.get_motor_collection().find_one_and_update(
            {"commit_id": commit.commit_id, "status": "reserving"},
            {"$set": {"status": "committing"}},
            return_document=ReturnDocument.AFTER,
        )
        if confirmed is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The commit reservation was released as abandoned; nothing was persisted",
            )
        commit.status = "committing"
        return None

    def commit_action_candidate(
        self,
        *,
        project_id: str,
        session_id: str,
        action_id: str,
        parameter_name: str,
        username: str,
        body: CommitAgentCandidateRequest,
    ) -> AgentCandidateCommitResponse:
        """Commit a revalidated task-result candidate with fail-closed auditing."""
        request_hash = self._candidate_commit_request_hash(
            action_id=action_id,
            parameter_name=parameter_name,
            body=body,
        )
        release_abandoned_reservations(project_id, session_id)
        existing = AgentCandidateCommitDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "idempotency_key": body.idempotency_key,
            }
        ).run()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was already used for a different candidate commit",
                )
            return self._candidate_commit_response(existing)

        session = self._get_session_document(project_id, session_id)
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        admission_refusal(session)
        if body.expected_state_version != session.state_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Agent session state version mismatch: "
                    f"expected {body.expected_state_version}, current {session.state_version}"
                ),
            )
        updates = update_authority(session, username) if body.autonomous else None
        candidates = self.list_action_candidates(
            project_id=project_id,
            session_id=session_id,
            action_id=action_id,
        )
        matches = [
            candidate
            for candidate in candidates.items
            if candidate.parameter_name == parameter_name and candidate.task_id == body.task_id
        ]
        if len(matches) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate does not uniquely match the authoritative task result",
            )
        candidate = matches[0]
        if not candidate.accepted:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Candidate gate rejected the value: {candidate.reason}",
            )
        evidence: dict[str, Any] = {}
        baseline: StoredParameter | None = None
        if updates is not None and body.decision_id is not None:
            grounds = check_commit(
                session=session,
                updates=updates,
                action=self._refresh_action_execution(
                    self._get_action_document(project_id, session_id, action_id)
                ),
                candidate=candidate,
                decision_id=body.decision_id,
                session_run_tasks=self._session_run_tasks(project_id, session_id),
                candidates_of=self._candidates_reader(project_id, session_id),
                evaluations_of=self._evaluations_of,
            )
            evidence, baseline = grounds.evidence, grounds.baseline
        else:
            check_required_evaluation(
                session,
                self._get_action_document(project_id, session_id, action_id),
                self._evaluations_of,
            )

        timestamp = now()
        commit = AgentCandidateCommitDocument(
            commit_id=str(uuid4()),
            session_id=session_id,
            action_id=action_id,
            project_id=project_id,
            idempotency_key=body.idempotency_key,
            request_hash=request_hash,
            execution_id=candidate.execution_id,
            task_id=candidate.task_id,
            task_name=candidate.task_name,
            chip_id=session.chip_id,
            qid=candidate.qid,
            parameter_name=candidate.parameter_name,
            value=candidate.value,
            status="reserving",
            reason="Candidate passed deterministic gate; waiting for the session gate",
            committed_by=username,
            state_version_before=session.state_version,
            state_version_after=session.state_version + 1,
            created_at=timestamp,
            authority="session_policy" if body.autonomous else "reviewed",
            decision_id=body.decision_id,
            assessment_evidence=evidence,
        )
        replay = self._reserve_commit(
            commit, session, request_hash, gone="candidate commit was being reserved"
        )
        if replay is not None:
            return self._candidate_commit_response(cast("AgentCandidateCommitDocument", replay))
        commit.reason = "Candidate passed deterministic gate; persistence reserved"

        stale_detail: str | None = None
        try:
            stored = read_parameter(
                project_id, session.chip_id, candidate.qid, candidate.parameter_name
            )
            if stored is None:
                raise ValueError(f"Qubit '{candidate.qid}' not found in chip '{session.chip_id}'")
            # An autonomous commit writes over the value its measurement started from; a
            # reviewed one over the value read here. Either way the write below is a
            # compare-and-set, so a write by anyone else in between is never overwritten.
            expected = baseline if baseline is not None else stored
            before = deepcopy(expected.value) if expected.present else None
            commit.before_snapshot = (
                before if isinstance(before, dict) or before is None else {"value": before}
            )

            parameter_snapshot: dict[str, Any] = {
                "parameter_name": candidate.parameter_name,
                "value": candidate.value,
                "error": candidate.error,
                "unit": candidate.unit,
                "value_type": candidate.value_type,
                "execution_id": candidate.execution_id,
                "task_id": candidate.task_id,
                "calibrated_at": timestamp,
            }
            after = compare_and_set_parameter(
                project_id=project_id,
                chip_id=session.chip_id,
                qid=candidate.qid,
                name=candidate.parameter_name,
                expected=expected,
                snapshot=parameter_snapshot,
                username=username,
            )
            if after is None:
                stale_detail = (
                    f"The stored {candidate.parameter_name} of {candidate.qid} changed before "
                    "the commit could write it; nothing was written. Read the session again "
                    "and measure again if the result may be stale."
                )
                raise ValueError(stale_detail)
            commit.after_snapshot = deepcopy(after)
            commit.status = "committed"
            commit.reason = "Candidate committed to authoritative QDash calibration state"
            commit.committed_at = now()
            commit.save()
        except Exception as exc:
            commit.status = "failed"
            commit.reason = f"Candidate persistence failed: {exc}"
            commit.save()
            if stale_detail is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{stale_detail} (audit record '{commit.commit_id}')",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Candidate commit failed after state reservation; "
                    f"audit record '{commit.commit_id}' was retained"
                ),
            ) from exc

        return self._candidate_commit_response(commit)

    def commit_candidate_set(
        self,
        *,
        project_id: str,
        session_id: str,
        username: str,
        body: CommitAgentCandidateSetRequest,
    ) -> AgentCandidateSetCommitResponse:
        """Commit one revalidated same-qubit candidate set in a single Qubit save."""
        request_hash = self._candidate_set_commit_request_hash(body)
        release_abandoned_reservations(project_id, session_id)
        existing = AgentCandidateSetCommitDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "idempotency_key": body.idempotency_key,
            }
        ).run()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was already used for a different candidate set commit",
                )
            return self._candidate_set_commit_response(existing)

        parameter_names = [reference.parameter_name for reference in body.candidates]
        if len(set(parameter_names)) != len(parameter_names):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate set commit contains duplicate parameter names",
            )

        session = self._get_session_document(project_id, session_id)
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        admission_refusal(session)
        if body.expected_state_version != session.state_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Agent session state version mismatch: "
                    f"expected {body.expected_state_version}, current {session.state_version}"
                ),
            )

        resolved: list[AgentCandidateResponse] = []
        for reference in body.candidates:
            candidates = self.list_action_candidates(
                project_id=project_id,
                session_id=session_id,
                action_id=reference.action_id,
            )
            matches = [
                candidate
                for candidate in candidates.items
                if candidate.parameter_name == reference.parameter_name
                and candidate.task_id == reference.task_id
            ]
            if len(matches) != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Candidate '{reference.parameter_name}' does not uniquely "
                        "match its authoritative task result"
                    ),
                )
            candidate = matches[0]
            if not candidate.accepted:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Candidate gate rejected '{candidate.parameter_name}': {candidate.reason}"
                    ),
                )
            check_required_evaluation(
                session,
                self._get_action_document(project_id, session_id, reference.action_id),
                self._evaluations_of,
            )
            resolved.append(candidate)

        qids = {candidate.qid for candidate in resolved}
        if len(qids) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate set must target exactly one qubit",
            )
        qid = next(iter(qids))
        if qid not in session.policy.qids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Candidate qid '{qid}' is outside the session scope",
            )

        timestamp = now()
        commit = AgentCandidateSetCommitDocument(
            commit_id=str(uuid4()),
            session_id=session_id,
            project_id=project_id,
            idempotency_key=body.idempotency_key,
            request_hash=request_hash,
            chip_id=session.chip_id,
            qid=qid,
            candidates=[candidate.model_dump(mode="json") for candidate in resolved],
            status="reserving",
            reason="Candidate set passed deterministic gates; waiting for the session gate",
            committed_by=username,
            state_version_before=session.state_version,
            state_version_after=session.state_version + 1,
            created_at=timestamp,
        )
        set_replay = self._reserve_commit(
            commit, session, request_hash, gone="candidate set commit was being reserved"
        )
        if set_replay is not None:
            return self._candidate_set_commit_response(
                cast("AgentCandidateSetCommitDocument", set_replay)
            )
        commit.reason = "Candidate set passed deterministic gates; persistence reserved"

        try:
            qubit = QubitDocument.find_one(
                {"project_id": project_id, "chip_id": session.chip_id, "qid": qid}
            ).run()
            if qubit is None:
                raise ValueError(f"Qubit '{qid}' not found in chip '{session.chip_id}'")
            commit.before_snapshot = {
                candidate.parameter_name: deepcopy(qubit.data.get(candidate.parameter_name))
                for candidate in resolved
            }
            output_parameters = {
                candidate.parameter_name: {
                    "parameter_name": candidate.parameter_name,
                    "value": candidate.value,
                    "error": candidate.error,
                    "unit": candidate.unit,
                    "value_type": candidate.value_type,
                    "execution_id": candidate.execution_id,
                    "task_id": candidate.task_id,
                    "calibrated_at": timestamp,
                }
                for candidate in resolved
            }
            updated_qubit = QubitDocument.update_calib_data(
                username=username,
                qid=qid,
                chip_id=session.chip_id,
                output_parameters=output_parameters,
                project_id=project_id,
            )
            commit.after_snapshot = {
                candidate.parameter_name: deepcopy(updated_qubit.data.get(candidate.parameter_name))
                for candidate in resolved
            }
            commit.status = "committed"
            commit.reason = "Candidate set committed to authoritative QDash state"
            commit.committed_at = now()
            commit.save()
        except Exception as exc:
            commit.status = "failed"
            commit.reason = f"Candidate persistence failed: {exc}"
            commit.save()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Candidate set commit failed after state reservation; "
                    f"audit record '{commit.commit_id}' was retained"
                ),
            ) from exc

        return self._candidate_set_commit_response(commit)

    def get_candidate_set_commit(
        self,
        *,
        project_id: str,
        session_id: str,
        commit_id: str,
    ) -> AgentCandidateSetCommitResponse:
        """Return one audited candidate-set commit."""
        self._get_session_document(project_id, session_id)
        commit = AgentCandidateSetCommitDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "commit_id": commit_id,
            }
        ).run()
        if commit is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent candidate set commit '{commit_id}' not found",
            )
        return self._candidate_set_commit_response(commit)

    def get_candidate_commit(
        self,
        *,
        project_id: str,
        session_id: str,
        commit_id: str,
    ) -> AgentCandidateCommitResponse:
        """Return one candidate commit and its worker-side apply state."""
        self._get_session_document(project_id, session_id)
        commit = AgentCandidateCommitDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "commit_id": commit_id,
            }
        ).run()
        if commit is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent candidate commit '{commit_id}' not found",
            )
        return self._candidate_commit_response(commit)

    async def apply_candidate_to_backend(
        self,
        *,
        project_id: str,
        session_id: str,
        commit_id: str,
        body: ApplyAgentCandidateRequest,
        flow_service: FlowService,
        username: str = "",
    ) -> AgentCandidateCommitResponse:
        """Dispatch a committed candidate to the worker-side backend apply flow."""
        request_hash = self._backend_apply_request_hash(body)
        session = self._get_session_document(project_id, session_id)
        release_abandoned_reservations(project_id, session_id)
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        admission_refusal(session)
        if body.expected_state_version != session.state_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Agent session state version mismatch: "
                    f"expected {body.expected_state_version}, current {session.state_version}"
                ),
            )

        commit = AgentCandidateCommitDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "commit_id": commit_id,
            }
        ).run()
        if commit is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent candidate commit '{commit_id}' not found",
            )
        if commit.status != "committed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Candidate commit is not committed: {commit.status}",
            )
        if commit.backend_apply_idempotency_key is not None:
            if (
                commit.backend_apply_idempotency_key == body.idempotency_key
                and commit.backend_apply_request_hash == request_hash
            ):
                return self._candidate_commit_response(commit)
            if commit.backend_status != "failed":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Candidate backend apply was already requested with different content",
                )
        if body.autonomous:
            check_apply(
                session=session,
                updates=update_authority(session, username),
                commit=commit,
                session_run_tasks=self._session_run_tasks(project_id, session_id),
                candidates_of=self._candidates_reader(project_id, session_id),
                evaluations_of=self._evaluations_of,
            )

        timestamp = now()
        token = str(uuid4())
        previous = AgentCandidateCommitDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "commit_id": commit_id,
                "status": "committed",
                # An autonomous apply never retries a failed one; that needs a person.
                "backend_status": {
                    "$in": ["not_started"] if body.autonomous else ["not_started", "failed"]
                },
            },
            {
                "$set": {
                    "backend_status": "dispatching",
                    "backend_apply_idempotency_key": body.idempotency_key,
                    "backend_apply_request_hash": request_hash,
                    "backend_push_to_github": body.push_to_github,
                    "backend_requested_at": timestamp,
                    "backend_operation_id": None,
                    "backend_error": "",
                    "backend_dispatch_token": token,
                    "backend_dispatch_confirmed": False,
                    "backend_authority": "session_policy" if body.autonomous else "reviewed",
                    "backend_requested_by": username or None,
                }
            },
            return_document=ReturnDocument.BEFORE,
        )
        if previous is None:
            latest = AgentCandidateCommitDocument.find_one(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "commit_id": commit_id,
                }
            ).run()
            if latest is None:
                raise HTTPException(status_code=404, detail="Agent candidate commit not found")
            if (
                latest.backend_apply_idempotency_key == body.idempotency_key
                and latest.backend_apply_request_hash == request_hash
            ):
                return self._candidate_commit_response(latest)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate backend apply is already in progress",
            )

        apply_chip = commit.chip_id or session.chip_id
        reservation = {"commit_id": commit_id, "backend_dispatch_token": token}
        commits = AgentCandidateCommitDocument.get_motor_collection()

        def restore() -> None:
            """Return an unconfirmed reservation to the previous apply state."""
            commits.update_one(
                {**reservation, "backend_dispatch_confirmed": False},
                {
                    "$set": {
                        field: previous.get(field)
                        for field in (
                            "backend_status",
                            "backend_apply_idempotency_key",
                            "backend_apply_request_hash",
                            "backend_push_to_github",
                            "backend_requested_at",
                            "backend_operation_id",
                            "backend_error",
                            "backend_authority",
                            "backend_requested_by",
                        )
                    }
                    | {"backend_dispatch_token": None, "backend_dispatch_confirmed": None},
                },
            )

        # One agent apply writes a chip's parameter files at a time, from this reservation
        # until the worker settles it (see qdash.dbmodel.agent_parameter_state).
        holder = acquire_backend_apply_lock(
            project_id=project_id,
            chip_id=apply_chip,
            session_id=session_id,
            commit_id=commit_id,
            token=token,
        )
        if holder is not None:
            restore()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"The backend apply of commit {holder} on chip {apply_chip} has not "
                    "settled; wait for it before another apply on the chip"
                ),
            )
        if not pass_execution_gate(project_id, session_id):
            # Paused or ended after the reservation: restore the previous apply state.
            restore()
            release_backend_apply_lock(apply_chip, commit_id, token)
            current = self._get_session_document(project_id, session_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {current.status.value}",
            )
        confirmed = commits.find_one_and_update(
            {**reservation, "backend_status": "dispatching", "backend_dispatch_confirmed": False},
            {"$set": {"backend_dispatch_confirmed": True}},
            return_document=ReturnDocument.AFTER,
        )
        if confirmed is None:
            release_backend_apply_lock(apply_chip, commit_id, token)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The backend apply reservation was released as abandoned; retry",
            )

        try:
            operation = await flow_service.execute_agent_candidate_apply(
                project_id=project_id,
                session_id=session_id,
                commit_id=commit_id,
                push_to_github=body.push_to_github,
            )
        except Exception as exc:
            commits.update_one(
                {**reservation, "project_id": project_id},
                {"$set": {"backend_status": "failed", "backend_error": str(exc)}},
            )
            release_backend_apply_lock(apply_chip, commit_id, token)
            raise

        commits.update_one(
            {**reservation, "project_id": project_id},
            {"$set": {"backend_operation_id": operation.execution_id}},
        )
        commits.update_one(
            {**reservation, "project_id": project_id, "backend_status": "dispatching"},
            {"$set": {"backend_status": "queued"}},
        )
        queued = AgentCandidateCommitDocument.find_one(
            {"project_id": project_id, "session_id": session_id, "commit_id": commit_id}
        ).run()
        if queued is None:
            raise HTTPException(status_code=500, detail="Candidate apply audit record disappeared")
        return self._candidate_commit_response(queued)

    def list_actions(
        self,
        *,
        project_id: str,
        session_id: str,
    ) -> ListAgentActionsResponse:
        """List the ordered audit trail for one agent session."""
        self._get_session_document(project_id, session_id)
        query = AgentActionDocument.find(
            {"project_id": project_id, "session_id": session_id},
            sort=[("created_at", SortDirection.ASCENDING)],
        )
        docs = cast("list[AgentActionDocument]", query.run())
        refreshed = [self._refresh_action_execution(doc) for doc in docs]
        return ListAgentActionsResponse(
            items=[self._action_response(doc) for doc in refreshed],
            total=len(refreshed),
        )

    def get_action(
        self, *, project_id: str, session_id: str, action_id: str
    ) -> AgentActionResponse:
        """Get one action and its current dispatch status."""
        action = self._get_action_document(project_id, session_id, action_id)
        return self._action_response(self._refresh_action_execution(action))

    async def execute_action(
        self,
        *,
        project_id: str,
        session_id: str,
        action_id: str,
        body: ExecuteAgentActionRequest,
        flow_service: FlowService,
        task_file_service: TaskFileService,
        username: str = "",
    ) -> AgentActionResponse:
        """Dispatch one authorized run-task action to the system workflow.

        The action runs the way the Task Workbench runs a task: inputs from the
        current calibration state, the session's readout_duration from the task,
        and the same override checks. Outputs stay staged for the candidate gate.

        The action is reserved (``dispatching``, unconfirmed), then the session gate is
        passed, then the reservation is confirmed and the run is dispatched. A pause that
        wins the session first makes the gate refuse, and the reservation is released.

        An autonomous dispatch (``body.autonomous``) also needs the signed-in user to have
        created the ``auto`` session, and no other measurement of the session may be
        dispatching or running. That check reads the other actions after this one is
        reserved, so of two concurrent dispatches at least one sees the other and is refused.
        """
        release_abandoned_reservations(project_id, session_id)
        action = AgentActionDocument.find_one(
            {"project_id": project_id, "session_id": session_id, "action_id": action_id}
        ).run()
        if action is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent action {action_id} not found"
            )
        if action.decision != AgentActionDecision.AUTHORIZED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only authorized agent actions can be executed",
            )
        if action.action_type != AgentActionType.RUN_TASK:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only run_task actions can be dispatched",
            )
        if action.execution_status != "not_started":
            return self._action_response(action)
        if action.task_name is None or len(action.qids) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The initial agent dispatcher supports exactly one target qid",
            )

        session = self._get_session_document(project_id, session_id)
        if body.autonomous:
            autonomous_session_refusal(session, username)
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        admission_refusal(session)
        if body.reconfigure and not session.policy.allow_reconfigure:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Hardware reconfiguration is not allowed by the agent session policy",
            )

        task, backend_name = resolve_catalog_task(task_file_service, action.task_name, None)
        input_overrides = _typed_overrides(task, action.parameter_overrides)

        token = str(uuid4())
        actions = AgentActionDocument.get_motor_collection()
        reserved = actions.find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "action_id": action_id,
                "execution_status": "not_started",
            },
            {
                "$set": {
                    "execution_status": "dispatching",
                    "dispatch_token": token,
                    "dispatch_confirmed": False,
                    "dispatch_reserved_at": now(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if reserved is None:
            latest = AgentActionDocument.find_one(
                {"project_id": project_id, "session_id": session_id, "action_id": action_id}
            ).run()
            if latest is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Agent action not found"
                )
            return self._action_response(latest)

        reservation = {"action_id": action_id, "dispatch_token": token}

        def release() -> None:
            # Nothing was dispatched; the action stays authorized for a later dispatch.
            actions.update_one(
                {**reservation, "dispatch_confirmed": False},
                {
                    "$set": {
                        "execution_status": "not_started",
                        "dispatch_token": None,
                        "dispatch_confirmed": None,
                        "dispatch_reserved_at": None,
                    }
                },
            )

        if not pass_execution_gate(project_id, session_id):
            # Paused or ended after the reservation.
            release()
            current = self._get_session_document(project_id, session_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {current.status.value}",
            )
        if body.autonomous:
            running = [
                other.action_id
                for other in self._session_run_tasks(project_id, session_id)
                if other.action_id != action_id
                and other.execution_status != "not_started"
                and other.execution_status not in FINISHED_RUN_STATUSES
            ]
            if running:
                release()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Action {', '.join(running)} of the session is being dispatched or "
                        "is still running; an autonomous step waits for its result"
                    ),
                )
        confirmed = actions.find_one_and_update(
            {**reservation, "execution_status": "dispatching", "dispatch_confirmed": False},
            {"$set": {"dispatch_confirmed": True}},
            return_document=ReturnDocument.AFTER,
        )
        if confirmed is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The dispatch reservation was released as abandoned; retry the action",
            )

        run_claim = None
        try:
            identity = None
            admitted_parent = (
                session.calibration_session_id
                if session.calibration_session_id
                and session.calibration_admission == CalibrationAdmission.ADMITTED
                else None
            )
            if admitted_parent is not None or session.records_runs:
                # The run of this dispatch, recorded before the launch so the worker stamps it:
                # in the calibration session the agent session was admitted to, or in none.
                # The agent session's gates above admitted it; the run only records it.
                run_claim, identity = RunLedger.begin_agent_action_run(
                    project_id=project_id,
                    calibration_session_id=admitted_parent,
                    chip_id=session.chip_id,
                    agent_session_id=session_id,
                    action_id=action_id,
                    requested_by=session.created_by,
                    run_name=f"{action.task_name} on {action.qids[0]}",
                )
            operation = await run_catalog_task(
                flow_service=flow_service,
                task=task,
                backend_name=backend_name,
                chip_id=session.chip_id,
                qid=action.qids[0],
                username=session.created_by,
                project_id=project_id,
                input_overrides=input_overrides,
                run_overrides={},
                update_calibration_parameters=False,
                update_params=body.update_params,
                reconfigure=body.reconfigure,
                execution_name=f"agent:{action.task_name}",
                tags=[f"agent-session:{session_id}"],
                calibration_run=identity,
                # A session created alone before agent actions recorded runs keeps its
                # executions to itself: no run is recorded for them.
                ungrouped=identity is None,
            )
        except Exception as exc:
            if run_claim is not None:
                RunLedger.settle_agent_action_run(run_claim, error=exc)
            actions.update_one(
                reservation,
                {
                    "$set": {
                        "execution_status": "failed",
                        "metadata.execution_error": str(exc),
                    }
                },
            )
            raise

        if run_claim is not None:
            RunLedger.settle_agent_action_run(run_claim, dispatched=operation)
        queued: dict[str, Any] = {
            "execution_status": "queued",
            "operation_id": operation.flow_run_id,
        }
        if body.source_execution_id:
            # Provenance only: the run reads the current calibration state.
            queued["metadata.source_execution_id"] = body.source_execution_id
        actions.update_one(reservation, {"$set": queued})
        dispatched = AgentActionDocument.find_one({"action_id": action_id}).run()
        if dispatched is None:
            raise HTTPException(status_code=500, detail="Agent action record disappeared")
        return self._action_response(self._refresh_action_execution(dispatched))
