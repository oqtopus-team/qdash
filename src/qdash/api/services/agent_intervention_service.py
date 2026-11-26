"""Durable human interventions for paused agent sessions.

An intervention records that an agent could not continue on its own: why, what it tried
(as references to actions, executions, task results, and evaluations), and what it asks.
Recording it pauses an active session (``waiting_for_human``), which blocks every further
action, dispatch, and commit for that session until an expert answers in QDash.

The expert either stops the session or authorizes a resume. A resume never widens the
session: it reactivates the same immutable policy, budget, and expiry, and for a plan with
a checkpoint it only authorizes a runner to continue. The session stays paused until a
runner claims the resume (``claim_resume``), so QDash never reports a plan as running
when nothing runs it.

Pausing is one atomic update of the session document: it moves the session to
``waiting_for_human``, points it at the new intervention, and stores the intervention record
as a pending payload. The record is written to its collection afterwards, and any later load
of the session writes it if a crash interrupted that step (see ``agent_session_gate``). So
the pause, not the record, is the decision, and every gate that requires an active session
is closed from that update on.

Several documents change for one response (the intervention and the session). The session
update is the single atomic decision; the intervention is written before it in a
``responding`` state and settled after it, and a read settles a response that a crash left
half applied. Slack delivery is recorded on the intervention after it is persisted, and a
failed delivery is retried without affecting the pause.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import Counter
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from bunnet import SortDirection
from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.agent_session import (
    AgentInterventionResponse,
    AgentNotificationDeliveryResponse,
    AgentResumeOption,
    ClaimAgentResumeRequest,
    CreateAgentInterventionRequest,
    ListAgentInterventionsResponse,
    RecordAgentResumeOutcomeRequest,
    RespondAgentInterventionRequest,
)
from qdash.api.services.agent_execution_links import resolve_chip_links
from qdash.api.services.agent_intervention_slack import AgentInterventionSlackNotifier
from qdash.api.services.agent_resume_policy import (
    PlanResumeFacts,
    node_budget_blocker,
    resume_blockers,
)
from qdash.api.services.agent_session_gate import (
    ADMITTED_FILTER,
    admission_refusal,
    autonomous_session_refusal,
    end_notification_update,
    in_flight_blockers,
    load_agent_session,
    materialize_pending_intervention,
    raw_document,
)
from qdash.api.services.agent_session_gate import to_bson as _bson
from qdash.common.utils.datetime import ensure_timezone, now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentInterventionDecision,
    AgentInterventionEvent,
    AgentInterventionReason,
    AgentInterventionResponseRecord,
    AgentInterventionStatus,
    AgentModelIdentity,
    AgentNotificationDelivery,
    AgentNotificationStatus,
    AgentResumeOutcomeRecord,
    AgentSessionLifecycleEvent,
    AgentSessionStatus,
)
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentInterventionDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.evaluation import EvaluationDocument
from qdash.dbmodel.evaluation_run import EvaluationRunDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.project import ProjectDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.datamodel.agent_session import AgentPlanCheckpoint

logger = logging.getLogger(__name__)

# A response or claim older than this is treated as abandoned by a crashed request.
RESPONDING_TIMEOUT = timedelta(seconds=60)
# How long one Slack attempt may hold the delivery before another attempt may start.
DELIVERY_LEASE = timedelta(seconds=120)
# Automatic Slack attempts before the delivery is marked failed and needs an explicit retry.
MAX_AUTOMATIC_DELIVERY_ATTEMPTS = 6
MAX_EVENTS = 100
# Pause attempts before giving up on a session whose state keeps changing.
MAX_PAUSE_ATTEMPTS = 5


def _delivery_backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** max(attempts - 1, 0), 1800))


_SAFE_ERROR_CODE = re.compile(r"[a-z0-9_.]{1,64}")


def _short_error(exc: BaseException) -> str:
    """A delivery error as its type and, for a Slack API error, Slack's error code.

    The exception text is never kept: a transport or client error may quote request
    headers, URLs, or tokens, and this summary is stored, returned by the API, and shown
    in the UI. Slack's ``error`` field is a fixed code such as ``channel_not_found``.
    """
    code: object = None
    response = getattr(exc, "response", None)
    try:
        code = response.get("error") if response is not None else None
    except Exception:
        code = None
    name = type(exc).__name__
    if isinstance(code, str) and _SAFE_ERROR_CODE.fullmatch(code):
        return f"{name}: {code}"
    return name


def _request_hash(body: CreateAgentInterventionRequest) -> str:
    # A request without the autonomous flag hashes as it did before the flag existed, so a
    # retry of an older request still matches its record. The reported model is provenance,
    # not part of the request: a retry keeps the first record's model.
    exclude = {"model"} if body.autonomous else {"autonomous", "model"}
    payload = json.dumps(
        body.model_dump(mode="json", exclude=exclude), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def plan_hash(checkpoint: AgentPlanCheckpoint) -> str:
    """Hash of the approved plan nodes, so a resumed run can prove it runs the same plan."""
    payload = json.dumps(
        [node.model_dump(mode="json") for node in checkpoint.nodes],
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


# The action key suffix the plan runner uses for node ``index``, visit ``visit``
# (agent_runner._run_plan): ``{prefix}-node-{index}[-visit-{visit}]-action``.
_PLAN_ACTION_SUFFIX = re.compile(r"(\d+)(?:-visit-(\d+))?-action")


def plan_identity(checkpoint: AgentPlanCheckpoint) -> dict[str, Any]:
    """The fields that identify one approved plan and its bounds; they never change."""
    return {
        "idempotency_prefix": checkpoint.idempotency_prefix,
        "plan_hash": plan_hash(checkpoint),
        "qid": checkpoint.qid,
        "source_execution_id": checkpoint.source_execution_id,
        "max_node_executions": checkpoint.max_node_executions,
        "max_node_visits": checkpoint.max_node_visits,
        "max_pre_dispatch_retries": checkpoint.max_pre_dispatch_retries,
        "commit_on_success": checkpoint.commit_on_success,
        "planner": checkpoint.planner,
    }


def plan_binding(checkpoint: AgentPlanCheckpoint, intervention_id: str) -> dict[str, Any]:
    """The session's record of its plan and the history its next checkpoint must extend."""
    return {
        "identity": plan_identity(checkpoint),
        "node_path": list(checkpoint.node_path),
        "planner_history_lengths": {
            node_id: len(history) for node_id, history in checkpoint.planner_history.items()
        },
        "intervention_id": intervention_id,
    }


class PlanHistory:
    """What QDash itself recorded of one plan: its run_task actions, by node and visit."""

    def __init__(self, checkpoint: AgentPlanCheckpoint, actions: list[AgentActionDocument]):
        """Attribute every run_task action of the session to a node visit of the plan."""
        self.visits: dict[str, int] = {}
        self.actions: dict[str, tuple[AgentActionDocument, int]] = {}
        self.errors: list[str] = []
        prefix = f"{checkpoint.idempotency_prefix}-node-"
        for action in actions:
            if action.action_type != AgentActionType.RUN_TASK:
                continue
            match = (
                _PLAN_ACTION_SUFFIX.fullmatch(action.idempotency_key[len(prefix) :])
                if action.idempotency_key.startswith(prefix)
                else None
            )
            if match is None:
                self.errors.append(
                    f"Action {action.action_id} ran outside plan {checkpoint.idempotency_prefix}"
                )
                continue
            index = int(match.group(1))
            visit = int(match.group(2) or 0)
            if index >= len(checkpoint.nodes):
                self.errors.append(f"Action {action.action_id} names plan node index {index}")
                continue
            node = checkpoint.nodes[index]
            if (
                action.task_name != node.task_name
                or action.qids != [checkpoint.qid]
                or not set(node.parameter_overrides) <= set(action.parameter_overrides)
            ):
                self.errors.append(
                    f"Action {action.action_id} does not match plan node {node.id} "
                    f"({node.task_name} on {checkpoint.qid})"
                )
                continue
            self.visits[node.id] = max(self.visits.get(node.id, 0), visit + 1)
            self.actions[action.action_id] = (action, index)

    @classmethod
    def load(cls, session: AgentSessionDocument, checkpoint: AgentPlanCheckpoint) -> PlanHistory:
        """Read the session's actions from QDash."""
        actions = cast(
            "list[AgentActionDocument]",
            AgentActionDocument.find(
                {
                    "project_id": session.project_id,
                    "session_id": session.session_id,
                    "action_type": AgentActionType.RUN_TASK.value,
                }
            ).run(),
        )
        return cls(checkpoint, actions)

    def node_visits(self, checkpoint: AgentPlanCheckpoint) -> dict[str, int]:
        """Visits per node: the larger of what the runner and QDash recorded."""
        return {
            node.id: max(checkpoint.visit_counts.get(node.id, 0), self.visits.get(node.id, 0))
            for node in checkpoint.nodes
        }

    def node_executions(self, checkpoint: AgentPlanCheckpoint) -> int:
        """Node executions so far: the larger of the runner's path and QDash's visits."""
        return max(len(checkpoint.node_path), sum(self.visits.values()))


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


CHECKPOINT_REJECTED = "checkpoint_rejected"


def _checkpoint_rejected(detail: str) -> HTTPException:
    """A checkpoint that QDash's records of the session's plan do not support.

    The detail carries ``code`` so a runner can tell this rejection from a malformed,
    unauthorized, or out-of-scope request and record the stop without a checkpoint.
    Nothing of the rejected checkpoint is stored, so such a record can never resume a plan.
    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": CHECKPOINT_REJECTED, "message": detail},
    )


class AgentInterventionService:
    """Record, answer, resume, and notify agent interventions."""

    def __init__(self, notifier: AgentInterventionSlackNotifier | None = None) -> None:
        """Initialize with the Slack notifier for the agent channel."""
        self._notifier = notifier or AgentInterventionSlackNotifier()

    @property
    def notifier(self) -> AgentInterventionSlackNotifier:
        """The agent channel notifier, shared with the session lifecycle messages."""
        return self._notifier

    # ------------------------------------------------------------------ lookups

    @staticmethod
    def _load_session(project_id: str, session_id: str) -> AgentSessionDocument:
        """Load a session, finish a half-written pause, and apply its expiry."""
        return load_agent_session(project_id, session_id)

    @staticmethod
    def _load(project_id: str, session_id: str, intervention_id: str) -> AgentInterventionDocument:
        doc = AgentInterventionDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "intervention_id": intervention_id,
            }
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent intervention '{intervention_id}' not found",
            )
        return doc

    @staticmethod
    def _collection() -> Any:
        return AgentInterventionDocument.get_motor_collection()

    @staticmethod
    def _event(actor: str, kind: str, detail: str = "") -> dict[str, Any]:
        event = AgentInterventionEvent(at=now(), actor=actor, kind=kind, detail=detail[:500])
        return cast("dict[str, Any]", _bson(event.model_dump()))

    def _push_event(self, intervention_id: str, actor: str, kind: str, detail: str = "") -> None:
        self._collection().update_one(
            {"intervention_id": intervention_id},
            {
                "$push": {
                    "events": {
                        "$each": [self._event(actor, kind, detail)],
                        "$slice": -MAX_EVENTS,
                    }
                },
                "$set": {"updated_at": now()},
            },
        )

    def _reload(self, intervention_id: str) -> AgentInterventionDocument:
        doc = AgentInterventionDocument.find_one({"intervention_id": intervention_id}).run()
        if doc is None:
            raise HTTPException(status_code=500, detail="Agent intervention record disappeared")
        return doc

    # ------------------------------------------------------------------ settling

    # The statuses a stop request closes: nothing answers or resumes them once it ended.
    _CLOSED_BY_STOP = (AgentInterventionStatus.OPEN, AgentInterventionStatus.RESUME_AUTHORIZED)

    def _close_for_stop(
        self, doc: AgentInterventionDocument, session: AgentSessionDocument
    ) -> bool:
        """Close one open or resume-authorized record of a session a stop request ended."""
        stop = session.stop
        if (
            stop is None
            or session.status != AgentSessionStatus.CANCELLED
            or doc.status not in self._CLOSED_BY_STOP
        ):
            return False
        result = self._collection().update_one(
            {"intervention_id": doc.intervention_id, "status": doc.status.value},
            {"$set": {"status": AgentInterventionStatus.STOPPED.value, "updated_at": now()}},
        )
        if result.modified_count != 1:
            return False
        self._push_event(
            doc.intervention_id,
            stop.stopped_by,
            "session_stopped",
            f"{stop.stopped_by} stopped the session: {stop.reason}",
        )
        return True

    def close_for_stopped_session(self, session: AgentSessionDocument) -> list[str]:
        """Close the session's open and resume-authorized records after a stop request.

        Idempotent. A record that was being answered when the stop won is rolled back to
        ``open`` by its response and closed by the next load (``_settle``).
        """
        if session.stop is None or session.status != AgentSessionStatus.CANCELLED:
            return []
        docs = AgentInterventionDocument.find(
            {
                "project_id": session.project_id,
                "session_id": session.session_id,
                "status": {"$in": [status.value for status in self._CLOSED_BY_STOP]},
            }
        ).run()
        return [doc.intervention_id for doc in docs if self._close_for_stop(doc, session)]

    def _settle(
        self, doc: AgentInterventionDocument, session: AgentSessionDocument
    ) -> AgentInterventionDocument:
        """Finish or roll back a response or claim that a crashed request left half applied."""
        timestamp = now()
        if self._close_for_stop(doc, session):
            return self._reload(doc.intervention_id)
        if doc.status == AgentInterventionStatus.RESPONDING and doc.response is not None:
            response = doc.response
            if session.intervention_resolution_id == response.response_id:
                self._collection().update_one(
                    {"intervention_id": doc.intervention_id, "status": "responding"},
                    {
                        "$set": {
                            "status": self._status_after_response(doc, response.decision).value,
                            "responding_since": None,
                            "updated_at": timestamp,
                        }
                    },
                )
                return self._reload(doc.intervention_id)
            since = ensure_timezone(doc.responding_since)
            if since is None or since + RESPONDING_TIMEOUT <= timestamp:
                self._collection().update_one(
                    {
                        "intervention_id": doc.intervention_id,
                        "status": "responding",
                        "response.response_id": response.response_id,
                    },
                    {
                        "$set": {
                            "status": AgentInterventionStatus.OPEN.value,
                            "response": None,
                            "responding_since": None,
                            "updated_at": timestamp,
                        }
                    },
                )
                return self._reload(doc.intervention_id)
        if (
            doc.status == AgentInterventionStatus.RESUME_AUTHORIZED
            and doc.response is not None
            and session.intervention_resolution_id == doc.response.response_id
            and session.resume_claim_key
            and session.active_intervention_id is None
            and session.status != AgentSessionStatus.WAITING_FOR_HUMAN
        ):
            # The runner's claim reactivated the session but did not finish the record.
            self._collection().update_one(
                {"intervention_id": doc.intervention_id, "status": "resume_authorized"},
                {
                    "$set": {
                        "status": AgentInterventionStatus.RESUMED.value,
                        "resume_claim_key": session.resume_claim_key,
                        "resumed_at": session.updated_at,
                        "updated_at": timestamp,
                    }
                },
            )
            return self._reload(doc.intervention_id)
        # A pausing record is only written after the update that paused the session for it,
        # so there is no record whose pause can still be missing.
        return doc

    @staticmethod
    def _status_after_response(
        doc: AgentInterventionDocument, decision: AgentInterventionDecision
    ) -> AgentInterventionStatus:
        if decision == AgentInterventionDecision.STOP:
            return AgentInterventionStatus.STOPPED
        if doc.checkpoint is None:
            return AgentInterventionStatus.RESUMED
        return AgentInterventionStatus.RESUME_AUTHORIZED

    # ------------------------------------------------------------------ resume checks

    def _resume_blockers(
        self,
        doc: AgentInterventionDocument,
        session: AgentSessionDocument,
        *,
        resume_node_id: str | None,
        expected_status: AgentInterventionStatus,
    ) -> list[str]:
        """Why a resume cannot happen now, in words an expert can act on."""
        plan: PlanResumeFacts | None = None
        checkpoint = doc.checkpoint
        if checkpoint is not None:
            binding = session.plan_binding
            history = PlanHistory.load(session, checkpoint)
            plan = PlanResumeFacts(
                checkpoint=checkpoint,
                approved=binding is not None
                and binding.get("identity") == plan_identity(checkpoint),
                history_errors=history.errors,
                node_visits=history.node_visits(checkpoint),
                node_executions=history.node_executions(checkpoint),
            )
        blockers = resume_blockers(
            intervention_id=doc.intervention_id,
            intervention_status=doc.status,
            expected_status=expected_status,
            session_status=session.status,
            active_intervention_id=session.active_intervention_id,
            action_count=session.action_count,
            max_actions=session.policy.max_actions,
            plan=plan,
            resume_node_id=resume_node_id,
        )
        # Read while the session is paused: no operation passes the execution gate between
        # this read and the update that resumes the session.
        blockers.extend(in_flight_blockers(doc.project_id, doc.session_id))
        return blockers

    # ------------------------------------------------------------------ responses

    def _resume_options(
        self, doc: AgentInterventionDocument, session: AgentSessionDocument
    ) -> list[AgentResumeOption]:
        """Every plan node with its visits, counted from the checkpoint and QDash's actions."""
        checkpoint = doc.checkpoint
        if checkpoint is None:
            return []
        node_visits = PlanHistory.load(session, checkpoint).node_visits(checkpoint)
        options = []
        for node in checkpoint.nodes:
            blocker = node_budget_blocker(checkpoint, node_visits, node.id)
            options.append(
                AgentResumeOption(
                    node_id=node.id,
                    task_name=node.task_name,
                    visits=node_visits.get(node.id, 0),
                    max_visits=checkpoint.max_node_visits,
                    available=blocker is None,
                    reason=blocker or "",
                )
            )
        return options

    @staticmethod
    def page_path(doc: AgentInterventionDocument) -> str:
        """The QDash UI path of the intervention page."""
        return f"/agent-sessions/{doc.session_id}/interventions/{doc.intervention_id}"

    def _response(
        self, doc: AgentInterventionDocument, session: AgentSessionDocument
    ) -> AgentInterventionResponse:
        blockers: list[str] = []
        if doc.status == AgentInterventionStatus.OPEN:
            blockers = self._resume_blockers(
                doc, session, resume_node_id=None, expected_status=AgentInterventionStatus.OPEN
            )
        resume_command = None
        if doc.checkpoint is not None and doc.status in {
            AgentInterventionStatus.RESUME_AUTHORIZED,
            AgentInterventionStatus.RESUMED,
        }:
            resume_command = (
                "qdash-agent --profile PROFILE resume-plan "
                f"--session-id {doc.session_id} --intervention-id {doc.intervention_id}"
            )
        data = doc.model_dump()
        notification = AgentNotificationDeliveryResponse.model_validate(
            doc.notification.model_dump()
        )
        return AgentInterventionResponse.model_validate(
            {
                **data,
                "notification": notification,
                "session_status": session.status,
                "session_state_version": session.state_version,
                "session_expires_at": session.expires_at,
                "actions_used": session.action_count,
                "max_actions": session.policy.max_actions,
                "can_resume": doc.status == AgentInterventionStatus.OPEN and not blockers,
                "resume_blockers": blockers,
                "resume_options": self._resume_options(doc, session),
                "resume_command": resume_command,
                "page_path": self.page_path(doc),
            }
        )

    # ------------------------------------------------------------------ validation

    @staticmethod
    def _validate_references(
        session: AgentSessionDocument, body: CreateAgentInterventionRequest
    ) -> None:
        """Check that every reference belongs to this project and session scope."""
        project_id = session.project_id
        policy = session.policy
        outside = sorted(set(body.qids) - set(policy.qids))
        if outside:
            raise _invalid(f"Targets are outside the session scope: {', '.join(outside)}")
        if body.task_name is not None and body.task_name not in policy.allowed_tasks:
            raise _invalid(f"Task '{body.task_name}' is outside the session scope")

        action_ids = {a.action_id for a in body.attempts if a.action_id}
        checkpoint = body.checkpoint
        if checkpoint is not None:
            action_ids |= {c.action_id for c in checkpoint.accepted_candidates}
            if checkpoint.qid not in policy.qids:
                raise _invalid(f"Checkpoint qid '{checkpoint.qid}' is outside the session scope")
            for node in checkpoint.nodes:
                if node.task_name not in policy.allowed_tasks:
                    raise _invalid(
                        f"Checkpoint node {node.id} task '{node.task_name}' is outside the "
                        "session scope"
                    )
            if checkpoint.planner == "evaluation" and policy.autonomy.value != "auto":
                raise _invalid(
                    "An evaluation-planned checkpoint needs a session with autonomy=auto"
                )
        actions: dict[str, AgentActionDocument] = {}
        if action_ids:
            actions = {
                doc.action_id: doc
                for doc in cast(
                    "list[AgentActionDocument]",
                    AgentActionDocument.find(
                        {
                            "project_id": project_id,
                            "session_id": session.session_id,
                            "action_id": {"$in": sorted(action_ids)},
                        }
                    ).run(),
                )
            }
            missing = sorted(action_ids - set(actions))
            if missing:
                raise _invalid(f"Actions are not part of this session: {', '.join(missing)}")

        AgentInterventionService._validate_attempt_evidence(session, body, actions)
        if checkpoint is not None and checkpoint.accepted_candidates:
            task_ids = {c.task_id for c in checkpoint.accepted_candidates}
            known = {
                doc.task_id
                for doc in cast(
                    "list[TaskResultHistoryDocument]",
                    TaskResultHistoryDocument.find(
                        {"project_id": project_id, "task_id": {"$in": sorted(task_ids)}}
                    ).run(),
                )
            }
            missing = sorted(task_ids - known)
            if missing:
                raise _invalid(f"Task results not found in this project: {', '.join(missing)}")
        if checkpoint is not None and checkpoint.source_execution_id:
            # Provenance only (the snapshot the plan was started from); it need not be one of
            # this session's executions, but it must be a real execution of the session's chip.
            source = ExecutionHistoryDocument.find_one(
                {
                    "project_id": project_id,
                    "chip_id": session.chip_id,
                    "execution_id": checkpoint.source_execution_id,
                }
            ).run()
            if source is None:
                raise _invalid(
                    f"Checkpoint source execution {checkpoint.source_execution_id} is not an "
                    f"execution of chip {session.chip_id} in this project"
                )
        if body.previous_intervention_id is not None:
            previous = AgentInterventionDocument.find_one(
                {
                    "project_id": project_id,
                    "session_id": session.session_id,
                    "intervention_id": body.previous_intervention_id,
                }
            ).run()
            if previous is None:
                raise _invalid("The previous intervention is not part of this session")
        # Last, so every reference, scope, and format failure above stays a plain 422 and
        # only a reconciliation failure carries code=checkpoint_rejected.
        if checkpoint is not None:
            AgentInterventionService._validate_checkpoint(session, checkpoint)

    @staticmethod
    def _validate_attempt_evidence(
        session: AgentSessionDocument,
        body: CreateAgentInterventionRequest,
        actions: dict[str, AgentActionDocument],
    ) -> None:
        """Check that each attempt's references form one chain of this session's evidence.

        An attempt's ``transition``, ``status``, and ``reason`` are what the client reports;
        QDash stores them as given. Its ids are evidence, and QDash checks them together
        rather than one by one:

        - the action belongs to this session, and its execution is the one QDash links to
          that action (``agent_execution_links``, so a claimed or ambiguous execution links
          nothing);
        - an execution cited without an action is one that an action of this session
          dispatched;
        - the task result came from that execution (or, without one, from an execution of
          this session), on the session's chip, for a target and task in its scope and the
          attempt's own ``qid`` and ``task_name``;
        - the evaluation evaluated that task result, and belongs to the cited run; a run
          cited without an evaluation evaluated the result's task on the session's chip.

        No field is required: an attempt that failed before dispatch, or before a result
        existed, cites only what it has. Every failure is a plain 422.
        """
        project_id = session.project_id
        policy = session.policy
        attempts = body.attempts
        if not attempts:
            return
        evaluation_ids = sorted({a.evaluation_id for a in attempts if a.evaluation_id})
        evaluations = (
            {
                doc.evaluation_id: doc
                for doc in cast(
                    "list[EvaluationDocument]",
                    EvaluationDocument.find(
                        {"project_id": project_id, "evaluation_id": {"$in": evaluation_ids}}
                    ).run(),
                )
            }
            if evaluation_ids
            else {}
        )
        missing = sorted(set(evaluation_ids) - set(evaluations))
        if missing:
            raise _invalid(f"Evaluations not found in this project: {', '.join(missing)}")
        run_ids = sorted({a.evaluation_run_id for a in attempts if a.evaluation_run_id})
        runs = (
            {
                doc.run_id: doc
                for doc in cast(
                    "list[EvaluationRunDocument]",
                    EvaluationRunDocument.find(
                        {"project_id": project_id, "run_id": {"$in": run_ids}}
                    ).run(),
                )
            }
            if run_ids
            else {}
        )
        missing = sorted(set(run_ids) - set(runs))
        if missing:
            raise _invalid(f"Evaluation runs not found in this project: {', '.join(missing)}")
        task_ids = sorted(
            {a.task_id for a in attempts if a.task_id}
            | {evaluations[a.evaluation_id].task_id for a in attempts if a.evaluation_id}
        )
        results = (
            {
                doc.task_id: doc
                for doc in cast(
                    "list[TaskResultHistoryDocument]",
                    TaskResultHistoryDocument.find(
                        {"project_id": project_id, "task_id": {"$in": task_ids}}
                    ).run(),
                )
            }
            if task_ids
            else {}
        )
        missing = sorted(set(task_ids) - set(results))
        if missing:
            raise _invalid(f"Task results not found in this project: {', '.join(missing)}")
        needs_links = any(a.execution_id or a.action_id for a in attempts) or bool(task_ids)
        links = resolve_chip_links(project_id, session.chip_id) if needs_links else None

        for index, attempt in enumerate(attempts):
            label = f"Attempt {index + 1}"
            if attempt.qid and attempt.qid not in policy.qids:
                raise _invalid(f"{label}: target {attempt.qid} is outside the session scope")
            if attempt.task_name and attempt.task_name not in policy.allowed_tasks:
                raise _invalid(f"{label}: task '{attempt.task_name}' is outside the session scope")
            action = actions.get(attempt.action_id) if attempt.action_id else None
            if action is not None and action.action_type == AgentActionType.RUN_TASK:
                if attempt.task_name and action.task_name != attempt.task_name:
                    raise _invalid(
                        f"{label}: action {action.action_id} ran {action.task_name}, "
                        f"not {attempt.task_name}"
                    )
                if attempt.qid and attempt.qid not in action.qids:
                    raise _invalid(
                        f"{label}: action {action.action_id} did not run on {attempt.qid}"
                    )

            # The execution the attempt stands for: the action's own, else the one cited.
            execution_id = attempt.execution_id
            if action is not None and links is not None:
                link = links.by_action.get(action.action_id)
                linked = link.execution_id if link is not None else None
                if execution_id and execution_id != linked:
                    raise _invalid(
                        f"{label}: execution {execution_id} is not the execution QDash links "
                        f"to action {action.action_id}"
                    )
                execution_id = execution_id or linked
            elif execution_id and links is not None:
                link = links.by_execution.get(execution_id)
                if link is None or link.session_id != session.session_id:
                    raise _invalid(
                        f"{label}: execution {execution_id} was not dispatched by this session"
                    )

            evaluation = evaluations.get(attempt.evaluation_id) if attempt.evaluation_id else None
            task_id = attempt.task_id
            if evaluation is not None:
                if task_id and evaluation.task_id != task_id:
                    raise _invalid(
                        f"{label}: evaluation {evaluation.evaluation_id} evaluated task result "
                        f"{evaluation.task_id}, not {task_id}"
                    )
                if attempt.evaluation_run_id and evaluation.run_id != attempt.evaluation_run_id:
                    raise _invalid(
                        f"{label}: evaluation {evaluation.evaluation_id} is not part of "
                        f"evaluation run {attempt.evaluation_run_id}"
                    )
                task_id = task_id or evaluation.task_id
            run = runs.get(attempt.evaluation_run_id) if attempt.evaluation_run_id else None
            if run is not None and not task_id:
                raise _invalid(
                    f"{label}: evaluation run {run.run_id} is cited without the task result "
                    "it evaluated"
                )
            if task_id is None:
                continue
            if action is not None and not execution_id:
                raise _invalid(
                    f"{label}: task result {task_id} cannot be linked to action "
                    f"{action.action_id} without its resolved execution"
                )
            result = results[task_id]
            if result.chip_id != session.chip_id or result.qid not in policy.qids:
                raise _invalid(
                    f"{label}: task result {task_id} is outside the session's chip and targets"
                )
            if attempt.qid and result.qid != attempt.qid:
                raise _invalid(
                    f"{label}: task result {task_id} is for {result.qid}, not {attempt.qid}"
                )
            if attempt.task_name and result.name != attempt.task_name:
                raise _invalid(
                    f"{label}: task result {task_id} is a {result.name} result, not "
                    f"{attempt.task_name}"
                )
            if execution_id:
                if result.execution_id != execution_id:
                    raise _invalid(
                        f"{label}: task result {task_id} did not come from execution {execution_id}"
                    )
            else:
                link = links.by_execution.get(result.execution_id) if links else None
                if link is None or link.session_id != session.session_id:
                    raise _invalid(
                        f"{label}: task result {task_id} did not come from an execution of "
                        "this session"
                    )
            if run is not None and (run.chip_id != session.chip_id or run.task_name != result.name):
                raise _invalid(
                    f"{label}: evaluation run {run.run_id} did not evaluate {result.name} "
                    f"on chip {session.chip_id}"
                )
            if evaluation is not None and (
                evaluation.chip_id != session.chip_id or evaluation.qid != result.qid
            ):
                raise _invalid(
                    f"{label}: evaluation {evaluation.evaluation_id} does not match task "
                    f"result {task_id}"
                )

    @staticmethod
    def _validate_checkpoint(
        session: AgentSessionDocument, checkpoint: AgentPlanCheckpoint
    ) -> None:
        """Reconcile a checkpoint with the session's plan and with QDash's own records.

        A session runs one approved plan. Its first checkpoint binds the plan's identity
        (prefix, nodes, and bounds) and every later one must name the same plan and extend
        the recorded path. Visit counts may be higher than QDash's actions show (a visit
        can end before its action reached QDash) but never lower, and every run_task
        action of the session must be a node visit of the plan, so neither a fresh prefix
        nor lowered counts restore a spent node budget. Carried candidates must come from
        the plan's own authorized runs, for the node's parameter, task, and target.

        A checkpoint that breaks the session policy or contradicts itself is invalid (plain
        422). One that is well formed but that QDash's records do not support, such as a
        session whose history mixes manual run_task actions with the plan's, is rejected
        with ``code=checkpoint_rejected`` (see ``_checkpoint_rejected``); those checks run
        last, so that code never covers a policy or self-consistency failure.
        """
        policy = session.policy
        if checkpoint.planner == "evaluation" and (
            checkpoint.max_node_visits is None
            or checkpoint.max_node_visits > policy.max_rounds_per_target
        ):
            raise _invalid(
                "An evaluation-planned checkpoint must limit node visits to the session's "
                f"{policy.max_rounds_per_target} rounds per target"
            )
        path_counts = Counter(checkpoint.node_path)
        if any(
            path_counts.get(node.id, 0) != checkpoint.visit_counts.get(node.id, 0)
            for node in checkpoint.nodes
        ):
            raise _invalid("The checkpoint's visit counts do not match its node path")
        candidates = checkpoint.accepted_candidates
        names = [candidate.parameter_name for candidate in candidates]
        if len(set(names)) != len(names):
            raise _invalid("The checkpoint carries more than one candidate per parameter")

        identity = plan_identity(checkpoint)
        binding = session.plan_binding
        if binding is not None:
            changed = sorted(
                key for key, value in identity.items() if binding["identity"].get(key) != value
            )
            if changed:
                raise _checkpoint_rejected(
                    "The checkpoint does not continue the plan this session approved "
                    f"(changed: {', '.join(changed)}); a newly authorized session is needed"
                )
            recorded_path = list(binding.get("node_path", []))
            if checkpoint.node_path[: len(recorded_path)] != recorded_path:
                raise _checkpoint_rejected(
                    "The checkpoint's node path does not extend the path QDash recorded for "
                    "this plan"
                )
            for node_id, length in binding.get("planner_history_lengths", {}).items():
                if len(checkpoint.planner_history.get(node_id, [])) < length:
                    raise _checkpoint_rejected(
                        f"The checkpoint drops planner verdicts recorded for node {node_id}"
                    )

        history = PlanHistory.load(session, checkpoint)
        if history.errors:
            raise _checkpoint_rejected(
                "The session ran actions that are not part of this plan, so the plan's "
                "budget cannot be checked: " + "; ".join(history.errors[:5])
            )
        lowered = sorted(
            f"{node_id} (checkpoint {checkpoint.visit_counts.get(node_id, 0)}, QDash {visits})"
            for node_id, visits in history.visits.items()
            if checkpoint.visit_counts.get(node_id, 0) < visits
        )
        if lowered:
            raise _checkpoint_rejected(
                "The checkpoint reports fewer node visits than QDash recorded: "
                + ", ".join(lowered)
            )

        results = (
            {
                doc.task_id: doc
                for doc in cast(
                    "list[TaskResultHistoryDocument]",
                    TaskResultHistoryDocument.find(
                        {
                            "project_id": session.project_id,
                            "task_id": {"$in": sorted({c.task_id for c in candidates})},
                        }
                    ).run(),
                )
            }
            if candidates
            else {}
        )
        for candidate in candidates:
            attributed = history.actions.get(candidate.action_id)
            if attributed is None:
                raise _checkpoint_rejected(
                    f"Checkpoint candidate {candidate.parameter_name} does not come from a "
                    "run of this plan"
                )
            action, index = attributed
            node = checkpoint.nodes[index]
            result = results.get(candidate.task_id)
            if (
                action.decision != AgentActionDecision.AUTHORIZED
                or node.candidate_parameter != candidate.parameter_name
                or result is None
                or action.execution_id is None
                or result.execution_id != action.execution_id
                or result.name != action.task_name
                or result.qid != checkpoint.qid
                or result.chip_id != session.chip_id
            ):
                raise _checkpoint_rejected(
                    f"Checkpoint candidate {candidate.parameter_name} does not match the "
                    f"authorized run, task result, and parameter of plan node {node.id}"
                )

    # ------------------------------------------------------------------ create

    def _initial_delivery(self) -> AgentNotificationDelivery:
        if self._notifier.is_enabled():
            return AgentNotificationDelivery(
                status=AgentNotificationStatus.PENDING, next_attempt_at=now()
            )
        return AgentNotificationDelivery(status=AgentNotificationStatus.DISABLED)

    @staticmethod
    def pause_update(
        doc: AgentInterventionDocument, *, action: AgentActionDocument | None = None
    ) -> dict[str, Any]:
        """The session fields that pause it on ``doc`` and carry the records to write."""
        return {
            "status": AgentSessionStatus.WAITING_FOR_HUMAN.value,
            "active_intervention_id": doc.intervention_id,
            "pending_intervention": {
                "intervention": raw_document(doc),
                "action": raw_document(action) if action is not None else None,
            },
        }

    def _find_by_key(
        self, project_id: str, session_id: str, idempotency_key: str
    ) -> AgentInterventionDocument | None:
        return AgentInterventionDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "idempotency_key": idempotency_key,
            }
        ).run()

    def _replay(
        self,
        existing: AgentInterventionDocument,
        session: AgentSessionDocument,
        request_hash: str,
    ) -> AgentInterventionResponse:
        if existing.request_hash != request_hash:
            raise _conflict("Idempotency key was already used for a different intervention")
        return self._response(self._settle(existing, session), session)

    def _new_document(
        self,
        *,
        session: AgentSessionDocument,
        username: str,
        body: CreateAgentInterventionRequest,
        request_hash: str,
        pauses: bool,
    ) -> AgentInterventionDocument:
        timestamp = now()
        return AgentInterventionDocument(
            intervention_id=str(uuid4()),
            project_id=session.project_id,
            session_id=session.session_id,
            chip_id=session.chip_id,
            idempotency_key=body.idempotency_key,
            request_hash=request_hash,
            created_by=username,
            reason=body.reason,
            summary=body.summary,
            question=body.question,
            node_id=body.node_id,
            task_name=body.task_name,
            qids=list(dict.fromkeys(body.qids)),
            attempts=body.attempts,
            previous_intervention_id=body.previous_intervention_id,
            checkpoint=body.checkpoint,
            plan_hash=plan_hash(body.checkpoint) if body.checkpoint else "",
            pauses_session=pauses,
            model=body.model,
            session_status_at_open=session.status,
            session_state_version_at_open=session.state_version,
            notification=self._initial_delivery(),
            events=[
                AgentInterventionEvent(
                    at=timestamp,
                    actor=username,
                    kind="created",
                    detail=(
                        "The session was paused"
                        if pauses
                        else f"Recorded on a {session.status.value} session; it cannot resume"
                    ),
                )
            ],
            created_at=timestamp,
            updated_at=timestamp,
        )

    def create_intervention(
        self,
        *,
        project_id: str,
        session_id: str,
        username: str,
        body: CreateAgentInterventionRequest,
    ) -> AgentInterventionResponse:
        """Pause an active session on a new intervention, or record it on an ended one.

        For an active session the pause and the record are one atomic session update (the
        record is written from it), so no action, dispatch, or commit can pass the session's
        gate once the intervention is accepted. Budgets and expiry never prevent recording:
        a session with no actions left, or one that expired, still gets the record, marked
        as not resumable. A retry with the same idempotency key returns the same record,
        including after a crash at any step.
        """
        request_hash = _request_hash(body)
        # Loading the session first writes a record that a crashed request left pending.
        session = self._load_session(project_id, session_id)
        existing = self._find_by_key(project_id, session_id, body.idempotency_key)
        if existing is not None:
            return self._replay(existing, session, request_hash)
        if body.autonomous:
            autonomous_session_refusal(session, username)
        for _ in range(MAX_PAUSE_ATTEMPTS):
            # Validated against each session state the pause is attempted on, so actions
            # recorded since an earlier attempt are reconciled too.
            self._validate_references(session, body)
            if session.status == AgentSessionStatus.WAITING_FOR_HUMAN:
                raise _conflict(
                    f"Agent session already waits on intervention {session.active_intervention_id}"
                )
            # A session never admitted in its calibration session records nothing: it has no
            # work to ask about, and a pause would lead to a resume.
            admission_refusal(session)
            if session.status != AgentSessionStatus.ACTIVE:
                return self._record_without_pause(
                    session=session, username=username, body=body, request_hash=request_hash
                )
            doc = self._new_document(
                session=session,
                username=username,
                body=body,
                request_hash=request_hash,
                pauses=True,
            )
            # The pause binds the plan (first checkpoint) or records how far it got; the
            # state version filter makes the check above and this update one decision.
            binding_update = (
                {"plan_binding": plan_binding(body.checkpoint, doc.intervention_id)}
                if body.checkpoint is not None
                else {}
            )
            paused = AgentSessionDocument.get_motor_collection().find_one_and_update(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "status": AgentSessionStatus.ACTIVE.value,
                    "state_version": session.state_version,
                    **ADMITTED_FILTER,
                },
                {
                    "$set": {**self.pause_update(doc), **binding_update, "updated_at": now()},
                    "$inc": {"state_version": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
            if paused is not None:
                session = self._load_session(project_id, session_id)
                return self._response(self._reload(doc.intervention_id), session)
            # Another update won; a concurrent request with the same key may have paused it.
            session = self._load_session(project_id, session_id)
            existing = self._find_by_key(project_id, session_id, body.idempotency_key)
            if existing is not None:
                return self._replay(existing, session, request_hash)
        raise _conflict("Agent session kept changing while the intervention was recorded")

    def _record_without_pause(
        self,
        *,
        session: AgentSessionDocument,
        username: str,
        body: CreateAgentInterventionRequest,
        request_hash: str,
    ) -> AgentInterventionResponse:
        """Record an intervention on a session that is no longer active; it cannot resume."""
        doc = self._new_document(
            session=session,
            username=username,
            body=body,
            request_hash=request_hash,
            pauses=False,
        )
        try:
            doc.insert()
        except DuplicateKeyError:
            existing = self._find_by_key(
                session.project_id, session.session_id, doc.idempotency_key
            )
            if existing is None:
                raise
            return self._replay(existing, session, request_hash)
        return self._response(doc, session)

    def build_request_human(
        self,
        *,
        session: AgentSessionDocument,
        action_id: str,
        username: str,
        diagnosis: str,
        model: AgentModelIdentity | None = None,
    ) -> AgentInterventionDocument:
        """The intervention of an authorized ``request_human`` action, not yet persisted.

        ``AgentSessionService.submit_action`` stores it in the same session update that
        pauses the session (see ``pause_update``).
        """
        timestamp = now()
        text = diagnosis.strip() or "The agent asked for a person without a diagnosis."
        return AgentInterventionDocument(
            intervention_id=str(uuid4()),
            project_id=session.project_id,
            session_id=session.session_id,
            chip_id=session.chip_id,
            idempotency_key=f"request-human:{action_id}",
            request_hash="",
            created_by=username,
            reason=AgentInterventionReason.AGENT_REQUEST,
            summary=text[:2000],
            question=text[:2000],
            action_id=action_id,
            pauses_session=True,
            model=model,
            session_status_at_open=session.status,
            session_state_version_at_open=session.state_version,
            notification=self._initial_delivery(),
            events=[
                AgentInterventionEvent(
                    at=timestamp,
                    actor=username,
                    kind="created",
                    detail="Requested with a request_human action",
                )
            ],
            created_at=timestamp,
            updated_at=timestamp,
        )

    # ------------------------------------------------------------------ read

    def list_interventions(
        self, *, project_id: str, session_id: str
    ) -> ListAgentInterventionsResponse:
        """List a session's interventions, newest first."""
        session = self._load_session(project_id, session_id)
        docs = cast(
            "list[AgentInterventionDocument]",
            AgentInterventionDocument.find(
                {"project_id": project_id, "session_id": session_id},
                sort=[("created_at", SortDirection.DESCENDING)],
            ).run(),
        )
        items = [self._response(self._settle(doc, session), session) for doc in docs]
        return ListAgentInterventionsResponse(items=items, total=len(items))

    def get_intervention(
        self, *, project_id: str, session_id: str, intervention_id: str
    ) -> AgentInterventionResponse:
        """Get one intervention with the session state needed to answer it."""
        session = self._load_session(project_id, session_id)
        doc = self._settle(self._load(project_id, session_id, intervention_id), session)
        return self._response(doc, session)

    # ------------------------------------------------------------------ respond

    def respond(
        self,
        *,
        project_id: str,
        session_id: str,
        intervention_id: str,
        username: str,
        body: RespondAgentInterventionRequest,
    ) -> AgentInterventionResponse:
        """Record an expert's answer and apply it to the session."""
        session = self._load_session(project_id, session_id)
        doc = self._settle(self._load(project_id, session_id, intervention_id), session)
        if doc.response is not None and doc.response.idempotency_key == body.idempotency_key:
            expected_node = None
            if body.decision == AgentInterventionDecision.RESUME and doc.checkpoint is not None:
                expected_node = body.resume_node_id or doc.checkpoint.stopped_node_id
            if (
                doc.response.decision == body.decision
                and doc.response.guidance == body.guidance
                and doc.response.resume_node_id == expected_node
            ):
                return self._response(doc, session)
            raise _conflict("Idempotency key was already used for a different response")
        if doc.status != AgentInterventionStatus.OPEN:
            raise _conflict(f"The intervention was already answered: {doc.status.value}")
        if body.expected_state_version != session.state_version:
            raise _conflict(
                "Agent session state version mismatch: "
                f"expected {body.expected_state_version}, current {session.state_version}; "
                "reload the intervention before answering"
            )

        resume_node_id: str | None = None
        if body.decision == AgentInterventionDecision.RESUME:
            if doc.checkpoint is None and body.resume_node_id is not None:
                raise _invalid("This intervention has no plan checkpoint to choose a node from")
            if doc.checkpoint is not None:
                resume_node_id = body.resume_node_id or doc.checkpoint.stopped_node_id
            blockers = self._resume_blockers(
                doc,
                session,
                resume_node_id=resume_node_id,
                expected_status=AgentInterventionStatus.OPEN,
            )
            if blockers:
                raise _conflict("Resume is not possible: " + "; ".join(blockers))

        timestamp = now()
        record = AgentInterventionResponseRecord(
            response_id=str(uuid4()),
            idempotency_key=body.idempotency_key,
            decision=body.decision,
            guidance=body.guidance,
            resume_node_id=resume_node_id,
            responded_by=username,
            responded_at=timestamp,
            expected_state_version=body.expected_state_version,
        )
        claimed = self._collection().find_one_and_update(
            {"intervention_id": intervention_id, "status": AgentInterventionStatus.OPEN.value},
            {
                "$set": {
                    "status": AgentInterventionStatus.RESPONDING.value,
                    "response": _bson(record.model_dump()),
                    "responding_since": timestamp,
                    "updated_at": timestamp,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if claimed is None:
            raise _conflict("Another response is being recorded for this intervention")

        paused_here = (
            session.status == AgentSessionStatus.WAITING_FOR_HUMAN
            and session.active_intervention_id == intervention_id
        )
        if paused_here:
            next_session: dict[str, Any] = {
                "intervention_resolution_id": record.response_id,
                "updated_at": timestamp,
            }
            if body.decision == AgentInterventionDecision.STOP:
                next_session |= {
                    "status": AgentSessionStatus.CANCELLED.value,
                    "active_intervention_id": None,
                    # The end message is stored by the update that ends the session.
                    **end_notification_update(
                        session, AgentSessionLifecycleEvent.CANCELLED, actor=username
                    ),
                }
            elif doc.checkpoint is None:
                next_session |= {
                    "status": AgentSessionStatus.ACTIVE.value,
                    "active_intervention_id": None,
                }
            updated = AgentSessionDocument.get_motor_collection().find_one_and_update(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "status": AgentSessionStatus.WAITING_FOR_HUMAN.value,
                    "state_version": body.expected_state_version,
                    "active_intervention_id": intervention_id,
                },
                {"$set": next_session, "$inc": {"state_version": 1}},
                return_document=ReturnDocument.AFTER,
            )
            if updated is None:
                self._collection().update_one(
                    {
                        "intervention_id": intervention_id,
                        "response.response_id": record.response_id,
                    },
                    {
                        "$set": {
                            "status": AgentInterventionStatus.OPEN.value,
                            "response": None,
                            "responding_since": None,
                            "updated_at": now(),
                        }
                    },
                )
                raise _conflict(
                    "Agent session changed while the response was recorded; reload and try again"
                )
        elif body.decision == AgentInterventionDecision.RESUME:
            # Unreachable after the blocker check; kept so a resume never passes silently.
            raise _conflict("Resume is not possible: the session is not paused on it")

        final_status = self._status_after_response(doc, body.decision)
        self._collection().update_one(
            {"intervention_id": intervention_id, "response.response_id": record.response_id},
            {
                "$set": {
                    "status": final_status.value,
                    "responding_since": None,
                    "updated_at": now(),
                }
            },
        )
        detail = {
            AgentInterventionStatus.STOPPED: (
                "Stopped the session" if paused_here else "Closed the record"
            ),
            AgentInterventionStatus.RESUMED: "Reactivated the session for the agent",
            AgentInterventionStatus.RESUME_AUTHORIZED: (
                f"Authorized a resume from node {resume_node_id}; waiting for the runner"
            ),
        }[final_status]
        self._push_event(intervention_id, username, body.decision.value, detail)
        session = self._load_session(project_id, session_id)
        return self._response(self._reload(intervention_id), session)

    # ------------------------------------------------------------------ resume

    def claim_resume(
        self,
        *,
        project_id: str,
        session_id: str,
        intervention_id: str,
        username: str,
        body: ClaimAgentResumeRequest,
    ) -> AgentInterventionResponse:
        """Reactivate the session for exactly one runner, after an authorized resume."""
        session = self._load_session(project_id, session_id)
        doc = self._settle(self._load(project_id, session_id, intervention_id), session)
        if doc.status == AgentInterventionStatus.RESUMED:
            if doc.resume_claim_key == body.claim_key:
                return self._response(doc, session)
            raise _conflict("Another runner already resumed this intervention")
        if doc.checkpoint is None or doc.response is None:
            raise _conflict("This intervention has no plan for a runner to resume")
        blockers = self._resume_blockers(
            doc,
            session,
            resume_node_id=doc.response.resume_node_id,
            expected_status=AgentInterventionStatus.RESUME_AUTHORIZED,
        )
        if session.intervention_resolution_id != doc.response.response_id:
            blockers.append("The session was changed by another response")
        if blockers:
            raise _conflict("Resume is not possible: " + "; ".join(blockers))

        timestamp = now()
        updated = AgentSessionDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "status": AgentSessionStatus.WAITING_FOR_HUMAN.value,
                "active_intervention_id": intervention_id,
                "intervention_resolution_id": doc.response.response_id,
                **ADMITTED_FILTER,
            },
            {
                "$set": {
                    "status": AgentSessionStatus.ACTIVE.value,
                    "active_intervention_id": None,
                    "resume_claim_key": body.claim_key,
                    "updated_at": timestamp,
                },
                "$inc": {"state_version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise _conflict("Agent session changed while the resume was claimed")
        self._collection().update_one(
            {"intervention_id": intervention_id, "status": "resume_authorized"},
            {
                "$set": {
                    "status": AgentInterventionStatus.RESUMED.value,
                    "resume_claim_key": body.claim_key,
                    "resumed_by": username,
                    "resumed_at": timestamp,
                    "updated_at": timestamp,
                }
            },
        )
        self._push_event(
            intervention_id,
            username,
            "resumed",
            f"A runner resumed the plan from node {doc.response.resume_node_id}",
        )
        session = self._load_session(project_id, session_id)
        return self._response(self._reload(intervention_id), session)

    def record_resume_outcome(
        self,
        *,
        project_id: str,
        session_id: str,
        intervention_id: str,
        username: str,
        body: RecordAgentResumeOutcomeRequest,
    ) -> AgentInterventionResponse:
        """Record how the resumed run ended, once, for the runner that claimed it."""
        session = self._load_session(project_id, session_id)
        doc = self._settle(self._load(project_id, session_id, intervention_id), session)
        if doc.status != AgentInterventionStatus.RESUMED:
            raise _conflict(f"The intervention was not resumed: {doc.status.value}")
        if doc.resume_claim_key != body.claim_key:
            raise _conflict("Only the runner that claimed the resume can record its outcome")
        if doc.resume_outcome is not None:
            same = (
                doc.resume_outcome.transition == body.transition
                and doc.resume_outcome.reason == body.reason
                and doc.resume_outcome.follow_up_intervention_id == body.follow_up_intervention_id
            )
            if same:
                return self._response(doc, session)
            raise _conflict("The resume outcome was already recorded")
        if body.follow_up_intervention_id is not None:
            follow_up = AgentInterventionDocument.find_one(
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "intervention_id": body.follow_up_intervention_id,
                    "previous_intervention_id": intervention_id,
                }
            ).run()
            if follow_up is None:
                raise _invalid("The follow-up intervention does not continue this one")
        outcome = AgentResumeOutcomeRecord(
            transition=body.transition,
            reason=body.reason,
            follow_up_intervention_id=body.follow_up_intervention_id,
            recorded_by=username,
            recorded_at=now(),
        )
        self._collection().update_one(
            {"intervention_id": intervention_id, "resume_outcome": None},
            {"$set": {"resume_outcome": _bson(outcome.model_dump()), "updated_at": now()}},
        )
        self._push_event(
            intervention_id, username, "resume_outcome", f"{body.transition}: {body.reason}"
        )
        return self._response(self._reload(intervention_id), session)

    # ------------------------------------------------------------------ Slack

    def deliver_notification(self, intervention_id: str, *, explicit: bool = False) -> None:
        """Send the Slack root message once, recording every attempt. Never raises.

        An attempt first takes a lease, so two API workers do not post at the same time. A
        sent message is never posted again. A request that times out after Slack accepted it
        cannot be told apart from a lost one, so a later retry may post a second message.
        """
        try:
            self._deliver(intervention_id, explicit=explicit)
        except Exception:
            logger.exception(
                "Agent intervention %s: Slack delivery bookkeeping failed", intervention_id
            )

    def _deliver(self, intervention_id: str, *, explicit: bool) -> None:
        timestamp = now()
        if not self._notifier.is_enabled():
            self._collection().update_one(
                {
                    "intervention_id": intervention_id,
                    "notification.status": {"$in": ["pending", "failed"]},
                },
                {"$set": {"notification.status": AgentNotificationStatus.DISABLED.value}},
            )
            return
        due: list[dict[str, Any]] = [
            {"notification.status": "sending", "notification.lease_until": {"$lt": timestamp}},
        ]
        if explicit:
            due.append({"notification.status": {"$in": ["pending", "failed", "disabled"]}})
        else:
            due.append(
                {
                    "notification.status": "pending",
                    "$or": [
                        {"notification.next_attempt_at": None},
                        {"notification.next_attempt_at": {"$lte": timestamp}},
                    ],
                }
            )
        leased = self._collection().find_one_and_update(
            {"intervention_id": intervention_id, "$or": due},
            {
                "$set": {
                    "notification.status": AgentNotificationStatus.SENDING.value,
                    "notification.lease_until": timestamp + DELIVERY_LEASE,
                    "notification.last_attempt_at": timestamp,
                },
                "$inc": {"notification.attempts": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if leased is None:
            return
        doc = self._reload(intervention_id)
        if doc.notification.message_ts:
            self._collection().update_one(
                {"intervention_id": intervention_id},
                {
                    "$set": {
                        "notification.status": AgentNotificationStatus.SENT.value,
                        "notification.lease_until": None,
                    }
                },
            )
            return
        project = ProjectDocument.find_by_id(doc.project_id)
        project_name = project.name if project is not None else doc.project_id
        try:
            channel_id, message_ts = self._notifier.post_root(doc, project_name=project_name)
        except Exception as exc:
            attempts = doc.notification.attempts
            exhausted = explicit or attempts >= MAX_AUTOMATIC_DELIVERY_ATTEMPTS
            self._collection().update_one(
                {"intervention_id": intervention_id},
                {
                    "$set": {
                        "notification.status": (
                            AgentNotificationStatus.FAILED.value
                            if exhausted
                            else AgentNotificationStatus.PENDING.value
                        ),
                        "notification.last_error": _short_error(exc),
                        "notification.lease_until": None,
                        "notification.next_attempt_at": (
                            None if exhausted else now() + _delivery_backoff(attempts)
                        ),
                    }
                },
            )
            logger.warning(
                "Agent intervention %s: Slack delivery attempt %d failed: %s",
                intervention_id,
                attempts,
                _short_error(exc),
            )
            return
        self._collection().update_one(
            {"intervention_id": intervention_id},
            {
                "$set": {
                    "notification.status": AgentNotificationStatus.SENT.value,
                    "notification.channel_id": channel_id,
                    "notification.message_ts": message_ts,
                    "notification.sent_at": now(),
                    "notification.last_error": "",
                    "notification.lease_until": None,
                    "notification.next_attempt_at": None,
                }
            },
        )

    def retry_notification(
        self, *, project_id: str, session_id: str, intervention_id: str, username: str
    ) -> AgentInterventionResponse:
        """Make one immediate delivery attempt for an unsent intervention."""
        session = self._load_session(project_id, session_id)
        doc = self._load(project_id, session_id, intervention_id)
        if not self._notifier.is_enabled():
            raise _conflict("Slack agent notifications are not configured on this deployment")
        if doc.notification.status == AgentNotificationStatus.SENT:
            return self._response(doc, session)
        lease = ensure_timezone(doc.notification.lease_until)
        if doc.notification.status == AgentNotificationStatus.SENDING and lease and lease > now():
            raise _conflict("A Slack delivery attempt is already in progress")
        self._push_event(intervention_id, username, "notification_retry")
        self.deliver_notification(intervention_id, explicit=True)
        return self._response(self._reload(intervention_id), session)

    def retry_due_notifications(self, *, limit: int = 20) -> int:
        """Attempt every delivery that is due; used by the API's background sweeper."""
        if not self._notifier.is_enabled():
            return 0
        # Write the records of pauses whose request crashed, so they are notified too.
        pending = cast(
            "list[AgentSessionDocument]",
            AgentSessionDocument.find({"pending_intervention": {"$ne": None}}, limit=limit).run(),
        )
        for session in pending:
            materialize_pending_intervention(session)
        timestamp = now()
        docs = cast(
            "list[AgentInterventionDocument]",
            AgentInterventionDocument.find(
                {
                    "$or": [
                        {
                            "notification.status": "pending",
                            "$or": [
                                {"notification.next_attempt_at": None},
                                {"notification.next_attempt_at": {"$lte": timestamp}},
                            ],
                        },
                        {
                            "notification.status": "sending",
                            "notification.lease_until": {"$lt": timestamp},
                        },
                    ]
                },
                limit=limit,
            ).run(),
        )
        for doc in docs:
            self.deliver_notification(doc.intervention_id)
        return len(docs)

    def post_update(self, intervention_id: str, text: str) -> None:
        """Reply in the Slack thread with a status update; failures are recorded. Never raises."""
        try:
            if not self._notifier.is_enabled():
                return
            doc = self._reload(intervention_id)
            if doc.notification.status != AgentNotificationStatus.SENT:
                # The root message, when it is sent, shows the current status.
                return
            try:
                self._notifier.post_reply(doc, text)
                error = ""
            except Exception as exc:
                error = _short_error(exc)
                logger.warning(
                    "Agent intervention %s: Slack reply failed: %s", intervention_id, error
                )
            self._collection().update_one(
                {"intervention_id": intervention_id},
                {"$set": {"notification.last_reply_error": error}},
            )
        except Exception:
            logger.exception(
                "Agent intervention %s: Slack reply bookkeeping failed", intervention_id
            )


NOTIFICATION_SWEEP_INTERVAL_SECONDS = 60.0


def run_notification_sweeper(
    service: AgentInterventionService | None = None,
    *,
    interval_seconds: float = NOTIFICATION_SWEEP_INTERVAL_SECONDS,
) -> asyncio.Task[None] | None:
    """Start the loop that retries due Slack deliveries, when agent notifications are on.

    The loop also sends due session start and end messages and expires overdue sessions.
    Each API worker runs its own loop; the delivery lease keeps two workers from posting the
    same message at once. Returns None when Slack agent notifications are not configured.
    """
    from qdash.api.services.agent_session_notifications import AgentSessionNotificationService

    sweeper_service = service or AgentInterventionService()
    if not sweeper_service._notifier.is_enabled():
        return None
    lifecycle = AgentSessionNotificationService(sweeper_service.notifier)

    async def sweep() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await asyncio.to_thread(sweeper_service.retry_due_notifications)
            except Exception:
                logger.exception("Agent intervention Slack sweep failed")
            try:
                # Expires overdue sessions too, so their end is announced without a reader.
                await asyncio.to_thread(lifecycle.sweep)
            except Exception:
                logger.exception("Agent session lifecycle Slack sweep failed")

    return asyncio.get_running_loop().create_task(sweep())
