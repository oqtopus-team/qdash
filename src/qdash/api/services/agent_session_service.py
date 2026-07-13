"""Application service for policy-governed local agent sessions."""

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

from qdash.api.schemas.agent_session import (
    AgentActionResponse,
    AgentCampaignCommitResponse,
    AgentCandidateCommitResponse,
    AgentCandidateResponse,
    AgentSessionResponse,
    ApplyAgentCandidateRequest,
    CandidateGateResponse,
    CommitAgentCampaignRequest,
    CommitAgentCandidateRequest,
    CreateAgentSessionRequest,
    EvaluateCandidateGateRequest,
    ExecuteAgentActionRequest,
    ListAgentActionsResponse,
    ListAgentCandidatesResponse,
    SubmitAgentActionRequest,
)
from qdash.common.agent_gate import evaluate_numeric_candidate
from qdash.common.utils.datetime import ensure_timezone, now
from qdash.datamodel.agent_session import (
    AgentActionDecision,
    AgentActionType,
    AgentSessionStatus,
)
from qdash.dbmodel.agent_session import (
    AgentActionDocument,
    AgentCampaignCommitDocument,
    AgentCandidateCommitDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.api.services.flow_service import FlowService


class AgentSessionService:
    """Authorize and audit actions proposed by user-operated local agents."""

    @staticmethod
    def _session_response(doc: AgentSessionDocument) -> AgentSessionResponse:
        return AgentSessionResponse.model_validate(doc.model_dump())

    @staticmethod
    def _action_response(doc: AgentActionDocument) -> AgentActionResponse:
        return AgentActionResponse.model_validate(doc.model_dump())

    @staticmethod
    def _candidate_commit_response(
        doc: AgentCandidateCommitDocument,
    ) -> AgentCandidateCommitResponse:
        return AgentCandidateCommitResponse.model_validate(doc.model_dump())

    @staticmethod
    def _campaign_commit_response(
        doc: AgentCampaignCommitDocument,
    ) -> AgentCampaignCommitResponse:
        return AgentCampaignCommitResponse.model_validate(doc.model_dump())

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
        execution = ExecutionHistoryDocument.find_one(
            {
                "project_id": doc.project_id,
                "note.flow_run_id": doc.operation_id,
            }
        ).run()
        if execution is None:
            return doc
        if doc.execution_id != execution.execution_id or doc.execution_status != execution.status:
            doc.execution_id = execution.execution_id
            doc.execution_status = execution.status
            doc.save()
        return doc

    @staticmethod
    def _request_hash(body: SubmitAgentActionRequest) -> str:
        payload = json.dumps(
            body.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _backend_apply_request_hash(body: ApplyAgentCandidateRequest) -> str:
        payload = json.dumps(
            body.model_dump(mode="json"),
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
                "body": body.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _campaign_commit_request_hash(body: CommitAgentCampaignRequest) -> str:
        payload = json.dumps(
            body.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _get_session_document(project_id: str, session_id: str) -> AgentSessionDocument:
        doc = AgentSessionDocument.find_one(
            {"project_id": project_id, "session_id": session_id}
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent session '{session_id}' not found",
            )
        expires_at = ensure_timezone(doc.expires_at)
        if (
            doc.status == AgentSessionStatus.ACTIVE
            and expires_at is not None
            and expires_at <= now()
        ):
            doc.status = AgentSessionStatus.EXPIRED
            doc.updated_at = now()
            doc.save()
        return doc

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

        policy = body.policy.model_copy(
            update={
                "qids": list(dict.fromkeys(body.policy.qids)),
                "allowed_tasks": list(dict.fromkeys(body.policy.allowed_tasks)),
                "allowed_actions": list(dict.fromkeys(body.policy.allowed_actions)),
            }
        )
        timestamp = now()
        doc = AgentSessionDocument(
            session_id=str(uuid4()),
            project_id=project_id,
            chip_id=body.chip_id,
            created_by=username,
            policy=policy,
            skill_name=body.skill_name,
            skill_version=body.skill_version,
            skill_hash=body.skill_hash,
            model_name=body.model_name,
            expires_at=timestamp + timedelta(seconds=body.expires_in_seconds),
            created_at=timestamp,
            updated_at=timestamp,
        )
        doc.insert()
        return self._session_response(doc)

    def get_session(self, *, project_id: str, session_id: str) -> AgentSessionResponse:
        """Get the authoritative state for an agent session."""
        return self._session_response(self._get_session_document(project_id, session_id))

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

    def submit_action(
        self,
        *,
        project_id: str,
        session_id: str,
        body: SubmitAgentActionRequest,
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
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        if body.expected_state_version != session.state_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Agent session state version mismatch: "
                    f"expected {body.expected_state_version}, current {session.state_version}"
                ),
            )

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
        updated = AgentSessionDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "status": AgentSessionStatus.ACTIVE.value,
                "state_version": session.state_version,
            },
            {
                "$set": {"status": next_status.value, "updated_at": timestamp},
                "$inc": {"state_version": 1, "action_count": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent session changed while the action was being authorized",
            )

        state_version_after = int(updated["state_version"])
        action = AgentActionDocument(
            action_id=str(uuid4()),
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
        )
        action.insert()
        return self._action_response(action)

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

        items: list[AgentCandidateResponse] = []
        for source_name, raw in sorted(task_result.output_parameters.items()):
            candidate = self._candidate_parameter(source_name, raw)
            if candidate is None:
                continue
            parameter_name, value, error, unit, value_type = candidate
            bounds = session.policy.allowed_overrides.get(parameter_name)
            if bounds is None:
                accepted = False
                reason = f"Parameter '{parameter_name}' is not allowed by the session policy"
                minimum = None
                maximum = None
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
                for metric_name, metric_bounds in session.policy.quality_gates.items():
                    metric_value = task_result.quality_metrics.get(metric_name)
                    if metric_value is None:
                        accepted = False
                        reason = f"Required quality metric '{metric_name}' is missing"
                        break
                    quality_decision = evaluate_numeric_candidate(
                        metric_value,
                        minimum=metric_bounds.minimum,
                        maximum=metric_bounds.maximum,
                    )
                    if not quality_decision.accepted:
                        accepted = False
                        reason = f"Quality metric '{metric_name}' {quality_decision.reason}"
                        break
                else:
                    if session.policy.quality_gates:
                        reason = "candidate passed deterministic bounds and quality gates"

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
                    accepted=accepted,
                    reason=reason,
                    minimum=minimum,
                    maximum=maximum,
                )
            )

        return ListAgentCandidatesResponse(items=items, total=len(items))

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
        if body.expected_state_version != session.state_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Agent session state version mismatch: "
                    f"expected {body.expected_state_version}, current {session.state_version}"
                ),
            )
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

        timestamp = now()
        updated_session = AgentSessionDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "status": AgentSessionStatus.ACTIVE.value,
                "state_version": session.state_version,
            },
            {
                "$set": {"updated_at": timestamp},
                "$inc": {"state_version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if updated_session is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent session changed while the candidate commit was being reserved",
            )

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
            status="committing",
            reason="Candidate passed deterministic gate; persistence reserved",
            committed_by=username,
            state_version_before=session.state_version,
            state_version_after=int(updated_session["state_version"]),
            created_at=timestamp,
        )
        commit.insert()

        try:
            qubit = QubitDocument.find_one(
                {
                    "project_id": project_id,
                    "chip_id": session.chip_id,
                    "qid": candidate.qid,
                }
            ).run()
            if qubit is None:
                raise ValueError(f"Qubit '{candidate.qid}' not found in chip '{session.chip_id}'")
            before = deepcopy(qubit.data.get(candidate.parameter_name))
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
            updated_qubit = QubitDocument.update_calib_data(
                username=username,
                qid=candidate.qid,
                chip_id=session.chip_id,
                output_parameters={candidate.parameter_name: parameter_snapshot},
                project_id=project_id,
            )
            after = deepcopy(updated_qubit.data.get(candidate.parameter_name))
            commit.after_snapshot = (
                after if isinstance(after, dict) or after is None else {"value": after}
            )
            commit.status = "committed"
            commit.reason = "Candidate committed to authoritative QDash calibration state"
            commit.committed_at = now()
            commit.save()
        except Exception as exc:
            commit.status = "failed"
            commit.reason = f"Candidate persistence failed: {exc}"
            commit.save()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Candidate commit failed after state reservation; "
                    f"audit record '{commit.commit_id}' was retained"
                ),
            ) from exc

        return self._candidate_commit_response(commit)

    def commit_campaign_candidates(
        self,
        *,
        project_id: str,
        session_id: str,
        username: str,
        body: CommitAgentCampaignRequest,
    ) -> AgentCampaignCommitResponse:
        """Commit one revalidated same-qubit candidate set in a single Qubit save."""
        request_hash = self._campaign_commit_request_hash(body)
        existing = AgentCampaignCommitDocument.find_one(
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
                    detail="Idempotency key was already used for a different campaign commit",
                )
            return self._campaign_commit_response(existing)

        parameter_names = [reference.parameter_name for reference in body.candidates]
        if len(set(parameter_names)) != len(parameter_names):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign commit contains duplicate parameter names",
            )

        session = self._get_session_document(project_id, session_id)
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
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
                        f"Campaign candidate '{reference.parameter_name}' does not uniquely "
                        "match its authoritative task result"
                    ),
                )
            candidate = matches[0]
            if not candidate.accepted:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Campaign candidate gate rejected '{candidate.parameter_name}': "
                        f"{candidate.reason}"
                    ),
                )
            resolved.append(candidate)

        qids = {candidate.qid for candidate in resolved}
        if len(qids) != 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign commit candidates must target exactly one qubit",
            )
        qid = next(iter(qids))
        if qid not in session.policy.qids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Campaign candidate qid '{qid}' is outside the session scope",
            )

        timestamp = now()
        updated_session = AgentSessionDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "status": AgentSessionStatus.ACTIVE.value,
                "state_version": session.state_version,
            },
            {"$set": {"updated_at": timestamp}, "$inc": {"state_version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if updated_session is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent session changed while the campaign commit was being reserved",
            )

        commit = AgentCampaignCommitDocument(
            commit_id=str(uuid4()),
            session_id=session_id,
            project_id=project_id,
            idempotency_key=body.idempotency_key,
            request_hash=request_hash,
            chip_id=session.chip_id,
            qid=qid,
            candidates=[candidate.model_dump(mode="json") for candidate in resolved],
            status="committing",
            reason="Campaign candidates passed deterministic gates; persistence reserved",
            committed_by=username,
            state_version_before=session.state_version,
            state_version_after=int(updated_session["state_version"]),
            created_at=timestamp,
        )
        commit.insert()

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
            commit.reason = "Campaign candidate set committed to authoritative QDash state"
            commit.committed_at = now()
            commit.save()
        except Exception as exc:
            commit.status = "failed"
            commit.reason = f"Campaign candidate persistence failed: {exc}"
            commit.save()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Campaign commit failed after state reservation; "
                    f"audit record '{commit.commit_id}' was retained"
                ),
            ) from exc

        return self._campaign_commit_response(commit)

    def get_campaign_commit(
        self,
        *,
        project_id: str,
        session_id: str,
        commit_id: str,
    ) -> AgentCampaignCommitResponse:
        """Return one audited campaign candidate-set commit."""
        self._get_session_document(project_id, session_id)
        commit = AgentCampaignCommitDocument.find_one(
            {
                "project_id": project_id,
                "session_id": session_id,
                "commit_id": commit_id,
            }
        ).run()
        if commit is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent campaign commit '{commit_id}' not found",
            )
        return self._campaign_commit_response(commit)

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
    ) -> AgentCandidateCommitResponse:
        """Dispatch a committed candidate to the worker-side backend apply flow."""
        request_hash = self._backend_apply_request_hash(body)
        session = self._get_session_document(project_id, session_id)
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
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

        timestamp = now()
        reserved = AgentCandidateCommitDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "commit_id": commit_id,
                "status": "committed",
                "backend_status": {"$in": ["not_started", "failed"]},
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
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if reserved is None:
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

        try:
            operation = await flow_service.execute_agent_candidate_apply(
                project_id=project_id,
                session_id=session_id,
                commit_id=commit_id,
                push_to_github=body.push_to_github,
            )
        except Exception as exc:
            AgentCandidateCommitDocument.get_motor_collection().update_one(
                {"project_id": project_id, "commit_id": commit_id},
                {"$set": {"backend_status": "failed", "backend_error": str(exc)}},
            )
            raise

        AgentCandidateCommitDocument.get_motor_collection().update_one(
            {"project_id": project_id, "commit_id": commit_id},
            {"$set": {"backend_operation_id": operation.execution_id}},
        )
        AgentCandidateCommitDocument.get_motor_collection().update_one(
            {
                "project_id": project_id,
                "commit_id": commit_id,
                "backend_status": "dispatching",
            },
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
    ) -> AgentActionResponse:
        """Dispatch one authorized run-task action to the system workflow."""
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
        if session.status != AgentSessionStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent session is not active: {session.status.value}",
            )
        if body.reconfigure and not session.policy.allow_reconfigure:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Hardware reconfiguration is not allowed by the agent session policy",
            )

        reserved = AgentActionDocument.get_motor_collection().find_one_and_update(
            {
                "project_id": project_id,
                "session_id": session_id,
                "action_id": action_id,
                "execution_status": "not_started",
            },
            {"$set": {"execution_status": "dispatching"}},
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

        try:
            operation = await flow_service.execute_single_task_from_snapshot(
                task_name=action.task_name,
                qid=action.qids[0],
                chip_id=session.chip_id,
                source_execution_id=body.source_execution_id,
                username=session.created_by,
                project_id=project_id,
                tags=[f"agent-session:{session_id}"],
                execution_name=f"agent:{action.task_name}",
                parameter_overrides={"input": action.parameter_overrides}
                if action.parameter_overrides
                else None,
                update_params=body.update_params,
                reconfigure=body.reconfigure,
            )
        except Exception as exc:
            action.execution_status = "failed"
            action.metadata = {**action.metadata, "execution_error": str(exc)}
            action.save()
            raise

        action.execution_status = "queued"
        action.operation_id = operation.execution_id
        action.save()
        return self._action_response(action)
