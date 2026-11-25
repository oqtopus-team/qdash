"""Commit gated task-result candidates of an agent session to calibration state.

A commit is reserved against the session's execution barrier (``agent_session_gate``)
before anything is persisted: the commit record is inserted as ``reserving``, a session
update that matches only an active session at the expected state version advances that
version, and the record is confirmed as ``committing``. Only then is calibration state
written, and the record is always settled as ``committed`` or ``failed`` so the audit
trail fails closed.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import uuid4

from fastapi import HTTPException, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.api.schemas.agent_session import (
    AgentCandidateCommitResponse,
    AgentCandidateResponse,
    AgentCandidateSetCommitResponse,
    CommitAgentCandidateRequest,
    CommitAgentCandidateSetRequest,
)
from qdash.api.services.agent_parameter_update import (
    check_commit,
    check_required_evaluation,
    update_authority,
)
from qdash.api.services.agent_session_gate import (
    ADMITTED_FILTER,
    admission_refusal,
    release_abandoned_reservations,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.agent_session import AgentSessionStatus
from qdash.dbmodel.agent_parameter_state import (
    StoredParameter,
    compare_and_set_parameter,
    read_parameter,
)
from qdash.dbmodel.agent_session import (
    AgentCandidateCommitDocument,
    AgentCandidateSetCommitDocument,
    AgentSessionDocument,
)
from qdash.dbmodel.qubit import QubitDocument

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from qdash.api.services.agent_session_service import AgentSessionService

CommitT = TypeVar("CommitT", AgentCandidateCommitDocument, AgentCandidateSetCommitDocument)


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def candidate_commit_request_hash(
    *, action_id: str, parameter_name: str, body: CommitAgentCandidateRequest
) -> str:
    """Hash one candidate commit request for idempotent replay."""
    return _hash(
        {
            "action_id": action_id,
            "parameter_name": parameter_name,
            # A reviewed request hashes as it did before autonomous commits existed.
            "body": body.model_dump(
                mode="json",
                exclude={"autonomous", "decision_id"} if not body.autonomous else set(),
            ),
        }
    )


def candidate_set_commit_request_hash(body: CommitAgentCandidateSetRequest) -> str:
    """Hash one candidate-set commit request for idempotent replay."""
    return _hash(body.model_dump(mode="json"))


def _find_by_key(
    model: type[CommitT], project_id: str, session_id: str, key: str
) -> CommitT | None:
    return model.find_one(
        {"project_id": project_id, "session_id": session_id, "idempotency_key": key}
    ).run()


def _replay(existing: CommitT, request_hash: str, *, conflict: str) -> CommitT:
    """Return the record a retry replays, or refuse a key reused for another request."""
    if existing.request_hash != request_hash:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict)
    return existing


def _require_active_at_version(session: AgentSessionDocument, expected_state_version: int) -> None:
    """Refuse unless the session is active, admitted, and at the caller's state version."""
    if session.status != AgentSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent session is not active: {session.status.value}",
        )
    admission_refusal(session)
    if expected_state_version != session.state_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Agent session state version mismatch: "
                f"expected {expected_state_version}, current {session.state_version}"
            ),
        )


def _parameter_snapshot(candidate: AgentCandidateResponse, timestamp: datetime) -> dict[str, Any]:
    """The stored form of a committed candidate."""
    return {
        "parameter_name": candidate.parameter_name,
        "value": candidate.value,
        "error": candidate.error,
        "unit": candidate.unit,
        "value_type": candidate.value_type,
        "execution_id": candidate.execution_id,
        "task_id": candidate.task_id,
        "calibrated_at": timestamp,
    }


def _record_failure(
    commit: AgentCandidateCommitDocument | AgentCandidateSetCommitDocument, exc: Exception
) -> None:
    """Settle a reserved commit as failed so its audit record is retained."""
    commit.status = "failed"
    commit.reason = f"Candidate persistence failed: {exc}"
    commit.save()


def _commit_response(doc: AgentCandidateCommitDocument) -> AgentCandidateCommitResponse:
    return AgentCandidateCommitResponse.model_validate(doc.model_dump())


def _set_commit_response(doc: AgentCandidateSetCommitDocument) -> AgentCandidateSetCommitResponse:
    return AgentCandidateSetCommitResponse.model_validate(doc.model_dump())


class AgentCandidateCommitService:
    """Reserve, persist, and audit candidate commits of one agent session service."""

    def __init__(self, sessions: AgentSessionService) -> None:
        """Read sessions, actions, candidates, and evaluations through ``sessions``."""
        self._sessions = sessions

    @staticmethod
    def _reserve_commit(
        commit: CommitT,
        session: AgentSessionDocument,
        request_hash: str,
        *,
        gone: str,
    ) -> CommitT | None:
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
            existing = _find_by_key(
                model, commit.project_id, commit.session_id, commit.idempotency_key
            )
            if existing is None:
                raise
            return _replay(
                existing,
                request_hash,
                conflict="Idempotency key was already used for a different candidate commit",
            )
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

    def _resolve_candidate(
        self,
        *,
        project_id: str,
        session_id: str,
        action_id: str,
        parameter_name: str,
        task_id: str,
        ambiguous: str,
        rejected: Callable[[AgentCandidateResponse], str],
    ) -> AgentCandidateResponse:
        """Re-gate the action's authoritative result and return its one accepted candidate."""
        candidates = self._sessions.list_action_candidates(
            project_id=project_id, session_id=session_id, action_id=action_id
        )
        matches = [
            candidate
            for candidate in candidates.items
            if candidate.parameter_name == parameter_name and candidate.task_id == task_id
        ]
        if len(matches) != 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ambiguous)
        candidate = matches[0]
        if not candidate.accepted:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=rejected(candidate))
        return candidate

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
        sessions = self._sessions
        request_hash = candidate_commit_request_hash(
            action_id=action_id, parameter_name=parameter_name, body=body
        )
        release_abandoned_reservations(project_id, session_id)
        existing = _find_by_key(
            AgentCandidateCommitDocument, project_id, session_id, body.idempotency_key
        )
        if existing is not None:
            return _commit_response(
                _replay(
                    existing,
                    request_hash,
                    conflict="Idempotency key was already used for a different candidate commit",
                ),
            )

        session = sessions._get_session_document(project_id, session_id)
        _require_active_at_version(session, body.expected_state_version)
        updates = update_authority(session, username) if body.autonomous else None
        candidate = self._resolve_candidate(
            project_id=project_id,
            session_id=session_id,
            action_id=action_id,
            parameter_name=parameter_name,
            task_id=body.task_id,
            ambiguous="Candidate does not uniquely match the authoritative task result",
            rejected=lambda c: f"Candidate gate rejected the value: {c.reason}",
        )
        evidence: dict[str, Any] = {}
        baseline: StoredParameter | None = None
        if updates is not None and body.decision_id is not None:
            grounds = check_commit(
                session=session,
                updates=updates,
                action=sessions._refresh_action_execution(
                    sessions._get_action_document(project_id, session_id, action_id)
                ),
                candidate=candidate,
                decision_id=body.decision_id,
                session_run_tasks=sessions._session_run_tasks(project_id, session_id),
                candidates_of=sessions._candidates_reader(project_id, session_id),
                evaluations_of=sessions._evaluations_of,
            )
            evidence, baseline = grounds.evidence, grounds.baseline
        else:
            check_required_evaluation(
                session,
                sessions._get_action_document(project_id, session_id, action_id),
                sessions._evaluations_of,
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
            return _commit_response(replay)
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
            after = compare_and_set_parameter(
                project_id=project_id,
                chip_id=session.chip_id,
                qid=candidate.qid,
                name=candidate.parameter_name,
                expected=expected,
                snapshot=_parameter_snapshot(candidate, timestamp),
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
            _record_failure(commit, exc)
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

        return _commit_response(commit)

    def commit_candidate_set(
        self,
        *,
        project_id: str,
        session_id: str,
        username: str,
        body: CommitAgentCandidateSetRequest,
    ) -> AgentCandidateSetCommitResponse:
        """Commit one revalidated same-qubit candidate set in a single Qubit save."""
        sessions = self._sessions
        request_hash = candidate_set_commit_request_hash(body)
        release_abandoned_reservations(project_id, session_id)
        existing = _find_by_key(
            AgentCandidateSetCommitDocument, project_id, session_id, body.idempotency_key
        )
        if existing is not None:
            return _set_commit_response(
                _replay(
                    existing,
                    request_hash,
                    conflict=(
                        "Idempotency key was already used for a different candidate set commit"
                    ),
                ),
            )

        parameter_names = [reference.parameter_name for reference in body.candidates]
        if len(set(parameter_names)) != len(parameter_names):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate set commit contains duplicate parameter names",
            )

        session = sessions._get_session_document(project_id, session_id)
        _require_active_at_version(session, body.expected_state_version)

        resolved: list[AgentCandidateResponse] = []
        for reference in body.candidates:
            candidate = self._resolve_candidate(
                project_id=project_id,
                session_id=session_id,
                action_id=reference.action_id,
                parameter_name=reference.parameter_name,
                task_id=reference.task_id,
                ambiguous=(
                    f"Candidate '{reference.parameter_name}' does not uniquely "
                    "match its authoritative task result"
                ),
                rejected=lambda c: f"Candidate gate rejected '{c.parameter_name}': {c.reason}",
            )
            check_required_evaluation(
                session,
                sessions._get_action_document(project_id, session_id, reference.action_id),
                sessions._evaluations_of,
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
        replay = self._reserve_commit(
            commit, session, request_hash, gone="candidate set commit was being reserved"
        )
        if replay is not None:
            return _set_commit_response(replay)
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
            updated_qubit = QubitDocument.update_calib_data(
                username=username,
                qid=qid,
                chip_id=session.chip_id,
                output_parameters={
                    candidate.parameter_name: _parameter_snapshot(candidate, timestamp)
                    for candidate in resolved
                },
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
            _record_failure(commit, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Candidate set commit failed after state reservation; "
                    f"audit record '{commit.commit_id}' was retained"
                ),
            ) from exc

        return _set_commit_response(commit)
