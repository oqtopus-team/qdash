"""Safe user-side runner for one agent calibration Skill step."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from qdash.client.services.client import QDashClient
    from qdash.client.services.models import (
        AgentActionResponse,
        AgentCandidateCommitResponse,
        AgentCandidateResponse,
    )


class AgentSkillTransition(StrEnum):
    """Deterministic transitions exposed to a Skill-orchestrating agent."""

    PASS = "pass"  # noqa: S105 - transition label, not a credential
    RETRY = "retry"
    ROLLBACK = "rollback"
    HUMAN_ESCALATION = "human_escalation"


@dataclass(frozen=True)
class AgentStepOutcome:
    """Outcome and provenance produced by one calibration Skill step."""

    transition: AgentSkillTransition
    reason: str
    session_id: str
    action_id: str | None = None
    operation_id: str | None = None
    execution_id: str | None = None
    action: AgentActionResponse | None = None
    candidate: AgentCandidateResponse | None = None
    commit: AgentCandidateCommitResponse | None = None


class AgentCalibrationRunner:
    """Run bounded single-task calibration steps through QDash safety gates."""

    def __init__(
        self,
        client: QDashClient,
        *,
        action_timeout_seconds: float = 120.0,
        execution_timeout_seconds: float = 600.0,
        backend_apply_timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._client = client
        self._action_timeout_seconds = action_timeout_seconds
        self._execution_timeout_seconds = execution_timeout_seconds
        self._backend_apply_timeout_seconds = backend_apply_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds

    def run_step(
        self,
        *,
        session_id: str,
        task_name: str,
        qid: str,
        source_execution_id: str,
        candidate_parameter: str,
        parameter_overrides: dict[str, float] | None = None,
        diagnosis: str = "",
        reconfigure_before_task: bool = False,
        commit_candidate: bool = False,
        apply_backend: bool = False,
        push_to_github: bool = True,
        action_idempotency_key: str | None = None,
        commit_idempotency_key: str | None = None,
        backend_apply_idempotency_key: str | None = None,
    ) -> AgentStepOutcome:
        """Run one staged measurement and return a typed Skill transition."""
        if apply_backend and not commit_candidate:
            raise ValueError("apply_backend requires commit_candidate=true")
        session = self._client.get_agent_session(session_id)
        action = self._client.submit_agent_action(
            session_id,
            idempotency_key=action_idempotency_key or f"action-{uuid4()}",
            expected_state_version=session.state_version,
            action_type="run_task",
            task_name=task_name,
            qids=[qid],
            parameter_overrides=parameter_overrides,
            diagnosis=diagnosis,
        )
        if action.decision != "authorized":
            return AgentStepOutcome(
                transition=AgentSkillTransition.HUMAN_ESCALATION,
                reason=action.reason,
                session_id=session_id,
                action_id=action.action_id,
                action=action,
            )

        dispatched = self._client.execute_agent_action(
            session_id,
            action.action_id,
            source_execution_id=source_execution_id,
            update_params=False,
            reconfigure=reconfigure_before_task,
        )
        if dispatched.execution_status == "failed":
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason=dispatched.reason,
                session_id=session_id,
                action_id=action.action_id,
                action=dispatched,
            )

        try:
            dispatched = self._client.wait_for_agent_action(
                session_id,
                action.action_id,
                timeout_seconds=self._action_timeout_seconds,
                poll_interval_seconds=self._poll_interval_seconds,
            )
        except TimeoutError as exc:
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason=str(exc),
                session_id=session_id,
                action_id=action.action_id,
                action=action,
            )

        operation_id = dispatched.operation_id
        if dispatched.execution_status == "failed" or operation_id is None:
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason="Agent action dispatch failed to produce an operation",
                session_id=session_id,
                action_id=action.action_id,
                action=dispatched,
            )

        try:
            dispatched = self._client.wait_for_agent_action_execution(
                session_id,
                action.action_id,
                timeout_seconds=self._execution_timeout_seconds,
                poll_interval_seconds=self._poll_interval_seconds,
            )
        except TimeoutError as exc:
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason=str(exc),
                session_id=session_id,
                action_id=action.action_id,
                operation_id=operation_id,
                action=dispatched,
            )
        execution_id = dispatched.execution_id
        if dispatched.execution_status == "failed" or execution_id is None:
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason="Agent operation failed to produce a QDash execution",
                session_id=session_id,
                action_id=action.action_id,
                operation_id=operation_id,
                execution_id=execution_id,
                action=dispatched,
            )

        try:
            execution = self._client.wait_for_execution(
                execution_id,
                timeout_seconds=self._execution_timeout_seconds,
                poll_interval_seconds=self._poll_interval_seconds,
            )
        except TimeoutError as exc:
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason=str(exc),
                session_id=session_id,
                action_id=action.action_id,
                operation_id=operation_id,
                execution_id=execution_id,
                action=dispatched,
            )
        if execution.status.lower() != "completed":
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason=f"Execution ended with status '{execution.status}'",
                session_id=session_id,
                action_id=action.action_id,
                operation_id=operation_id,
                execution_id=execution_id,
                action=dispatched,
            )

        candidates = self._client.list_agent_action_candidates(session_id, action.action_id)
        matches = [
            candidate for candidate in candidates if candidate.parameter_name == candidate_parameter
        ]
        if len(matches) != 1:
            return AgentStepOutcome(
                transition=AgentSkillTransition.RETRY,
                reason=(
                    f"Expected one authoritative candidate for '{candidate_parameter}', "
                    f"found {len(matches)}"
                ),
                session_id=session_id,
                action_id=action.action_id,
                operation_id=operation_id,
                execution_id=execution_id,
                action=dispatched,
            )

        candidate = matches[0]
        if not candidate.accepted:
            return AgentStepOutcome(
                transition=AgentSkillTransition.ROLLBACK,
                reason=candidate.reason,
                session_id=session_id,
                action_id=action.action_id,
                operation_id=operation_id,
                execution_id=execution_id,
                action=dispatched,
                candidate=candidate,
            )

        committed = None
        if commit_candidate:
            current_session = self._client.get_agent_session(session_id)
            committed = self._client.commit_agent_action_candidate(
                session_id,
                action.action_id,
                candidate.parameter_name,
                idempotency_key=commit_idempotency_key or f"commit-{uuid4()}",
                expected_state_version=current_session.state_version,
                task_id=candidate.task_id,
            )
            if apply_backend:
                apply_session = self._client.get_agent_session(session_id)
                committed = self._client.apply_agent_candidate_commit(
                    session_id,
                    committed.commit_id,
                    idempotency_key=(backend_apply_idempotency_key or f"backend-apply-{uuid4()}"),
                    expected_state_version=apply_session.state_version,
                    push_to_github=push_to_github,
                )
                try:
                    committed = self._client.wait_for_agent_candidate_apply(
                        session_id,
                        committed.commit_id,
                        timeout_seconds=self._backend_apply_timeout_seconds,
                        poll_interval_seconds=self._poll_interval_seconds,
                    )
                except TimeoutError as exc:
                    return AgentStepOutcome(
                        transition=AgentSkillTransition.RETRY,
                        reason=str(exc),
                        session_id=session_id,
                        action_id=action.action_id,
                        operation_id=operation_id,
                        action=dispatched,
                        candidate=candidate,
                        commit=committed,
                    )
                if committed.backend_status != "applied" or not committed.backend_verified:
                    return AgentStepOutcome(
                        transition=AgentSkillTransition.HUMAN_ESCALATION,
                        reason=(
                            committed.backend_error
                            or "Backend application failed deterministic verification"
                        ),
                        session_id=session_id,
                        action_id=action.action_id,
                        operation_id=operation_id,
                        action=dispatched,
                        candidate=candidate,
                        commit=committed,
                    )

        return AgentStepOutcome(
            transition=AgentSkillTransition.PASS,
            reason=(
                "Candidate passed, was committed, and backend-verified"
                if committed is not None and committed.backend_status == "applied"
                else (
                    "Candidate passed and was committed"
                    if committed is not None
                    else "Candidate passed and remains staged"
                )
            ),
            session_id=session_id,
            action_id=action.action_id,
            operation_id=operation_id,
            execution_id=execution_id,
            action=dispatched,
            candidate=candidate,
            commit=committed,
        )
