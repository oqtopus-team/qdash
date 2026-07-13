"""Safe user-side runner for one agent calibration Skill step."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from qdash.client.services.errors import QDashApiError, QDashTransportError

if TYPE_CHECKING:
    from qdash.client.services.client import QDashClient
    from qdash.client.services.models import (
        AgentActionResponse,
        AgentCandidateCommitResponse,
        AgentCandidateResponse,
        AgentSessionResponse,
    )

_CAMPAIGN_COMPLETE = "$complete"


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


@dataclass(frozen=True)
class AgentCampaignNode:
    """One policy-bounded node in an autonomous single-qubit campaign."""

    task_name: str
    candidate_parameter: str
    node_id: str | None = None
    on_pass: str | None = None
    on_rollback: str | None = None
    parameter_overrides: dict[str, float] = field(default_factory=dict)
    diagnosis: str = ""
    reconfigure_before_task: bool = False
    commit_candidate: bool = False
    apply_backend: bool = False
    push_to_github: bool = False

    def __post_init__(self) -> None:
        if not self.task_name:
            raise ValueError("campaign task_name must not be empty")
        if not self.candidate_parameter:
            raise ValueError("campaign candidate_parameter must not be empty")
        if self.apply_backend and not self.commit_candidate:
            raise ValueError("campaign apply_backend requires commit_candidate=true")
        if self.push_to_github and not self.apply_backend:
            raise ValueError("campaign push_to_github requires apply_backend=true")
        for field_name, value in (
            ("node_id", self.node_id),
            ("on_pass", self.on_pass),
            ("on_rollback", self.on_rollback),
        ):
            if value is not None and not value:
                raise ValueError(f"campaign {field_name} must not be empty")
        if any(not math.isfinite(value) for value in self.parameter_overrides.values()):
            raise ValueError("campaign parameter overrides must be finite")


@dataclass(frozen=True)
class AgentCampaignOutcome:
    """Terminal campaign result with every attempted Skill transition."""

    transition: AgentSkillTransition
    reason: str
    session_id: str
    qid: str
    source_execution_id: str
    completed_nodes: int
    attempts: int
    outcomes: tuple[AgentStepOutcome, ...]
    carried_overrides: dict[str, float] = field(default_factory=dict)
    node_path: tuple[str, ...] = ()


def _api_error_outcome(
    exc: QDashApiError,
    *,
    session_id: str,
    action_id: str | None = None,
    operation_id: str | None = None,
    execution_id: str | None = None,
    action: AgentActionResponse | None = None,
    candidate: AgentCandidateResponse | None = None,
    commit: AgentCandidateCommitResponse | None = None,
) -> AgentStepOutcome:
    status = exc.status_code
    is_transient = isinstance(exc, QDashTransportError) and (
        status is None or status in {408, 429} or status >= 500
    )
    transition = (
        AgentSkillTransition.RETRY if is_transient else AgentSkillTransition.HUMAN_ESCALATION
    )
    return AgentStepOutcome(
        transition=transition,
        reason=f"QDash API request failed: {exc}",
        session_id=session_id,
        action_id=action_id,
        operation_id=operation_id,
        execution_id=execution_id,
        action=action,
        candidate=candidate,
        commit=commit,
    )


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
        push_to_github: bool = False,
        action_idempotency_key: str | None = None,
        commit_idempotency_key: str | None = None,
        backend_apply_idempotency_key: str | None = None,
    ) -> AgentStepOutcome:
        """Run one staged measurement and return a typed Skill transition."""
        if apply_backend and not commit_candidate:
            raise ValueError("apply_backend requires commit_candidate=true")
        try:
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
        except QDashApiError as exc:
            return _api_error_outcome(exc, session_id=session_id)
        if action.decision != "authorized":
            return AgentStepOutcome(
                transition=AgentSkillTransition.HUMAN_ESCALATION,
                reason=action.reason,
                session_id=session_id,
                action_id=action.action_id,
                action=action,
            )

        try:
            dispatched = self._client.execute_agent_action(
                session_id,
                action.action_id,
                source_execution_id=source_execution_id,
                update_params=False,
                reconfigure=reconfigure_before_task,
            )
        except QDashApiError as exc:
            return _api_error_outcome(
                exc,
                session_id=session_id,
                action_id=action.action_id,
                action=action,
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

        except QDashApiError as exc:
            return _api_error_outcome(
                exc,
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
        except QDashApiError as exc:
            return _api_error_outcome(
                exc,
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
        except QDashApiError as exc:
            return _api_error_outcome(
                exc,
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

        try:
            candidates = self._client.list_agent_action_candidates(session_id, action.action_id)
        except QDashApiError as exc:
            return _api_error_outcome(
                exc,
                session_id=session_id,
                action_id=action.action_id,
                operation_id=operation_id,
                execution_id=execution_id,
                action=dispatched,
            )
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
            try:
                current_session = self._client.get_agent_session(session_id)
                committed = self._client.commit_agent_action_candidate(
                    session_id,
                    action.action_id,
                    candidate.parameter_name,
                    idempotency_key=commit_idempotency_key or f"commit-{uuid4()}",
                    expected_state_version=current_session.state_version,
                    task_id=candidate.task_id,
                )
            except QDashApiError as exc:
                return _api_error_outcome(
                    exc,
                    session_id=session_id,
                    action_id=action.action_id,
                    operation_id=operation_id,
                    execution_id=execution_id,
                    action=dispatched,
                    candidate=candidate,
                )
            if apply_backend:
                try:
                    apply_session = self._client.get_agent_session(session_id)
                    committed = self._client.apply_agent_candidate_commit(
                        session_id,
                        committed.commit_id,
                        idempotency_key=(
                            backend_apply_idempotency_key or f"backend-apply-{uuid4()}"
                        ),
                        expected_state_version=apply_session.state_version,
                        push_to_github=push_to_github,
                    )
                except QDashApiError as exc:
                    return _api_error_outcome(
                        exc,
                        session_id=session_id,
                        action_id=action.action_id,
                        operation_id=operation_id,
                        execution_id=execution_id,
                        action=dispatched,
                        candidate=candidate,
                        commit=committed,
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
                        execution_id=execution_id,
                        action=dispatched,
                        candidate=candidate,
                        commit=committed,
                    )
                except QDashApiError as exc:
                    return _api_error_outcome(
                        exc,
                        session_id=session_id,
                        action_id=action.action_id,
                        operation_id=operation_id,
                        execution_id=execution_id,
                        action=dispatched,
                        candidate=candidate,
                        commit=committed,
                    )
                if committed.backend_status != "applied" or not committed.backend_verified:
                    return AgentStepOutcome(
                        execution_id=execution_id,
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


class AgentCampaignRunner:
    """Advance a declarative single-qubit campaign through typed transitions."""

    def __init__(
        self,
        client: QDashClient,
        *,
        step_runner: AgentCalibrationRunner | None = None,
        action_timeout_seconds: float = 120.0,
        execution_timeout_seconds: float = 600.0,
        backend_apply_timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self._client = client
        self._step_runner = step_runner or AgentCalibrationRunner(
            client,
            action_timeout_seconds=action_timeout_seconds,
            execution_timeout_seconds=execution_timeout_seconds,
            backend_apply_timeout_seconds=backend_apply_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    @staticmethod
    def _validate_graph(nodes: list[AgentCampaignNode]) -> tuple[list[str], str | None]:
        node_ids = [node.node_id or f"node-{index}" for index, node in enumerate(nodes)]
        if _CAMPAIGN_COMPLETE in node_ids:
            return node_ids, f"Campaign node ID '{_CAMPAIGN_COMPLETE}' is reserved"
        if len(set(node_ids)) != len(node_ids):
            return node_ids, "Campaign node IDs must be unique"

        known_ids = set(node_ids)
        for index, node in enumerate(nodes):
            for transition, target in (
                ("on_pass", node.on_pass),
                ("on_rollback", node.on_rollback),
            ):
                if (
                    target is not None
                    and not (transition == "on_pass" and target == _CAMPAIGN_COMPLETE)
                    and target not in known_ids
                ):
                    return (
                        node_ids,
                        f"Node {index} {transition} target '{target}' does not exist",
                    )
        return node_ids, None

    @staticmethod
    def _policy_error(
        session: AgentSessionResponse,
        qid: str,
        nodes: list[AgentCampaignNode],
        required_actions: int,
    ) -> str | None:
        policy = session.policy
        if session.status != "active":
            return f"Agent session is not active: {session.status}"
        if qid not in policy.qids:
            return f"Qid '{qid}' is outside the session scope"
        remaining_actions = policy.max_actions - session.action_count
        if required_actions > remaining_actions:
            return (
                f"Campaign requires {required_actions} actions but the session has "
                f"{remaining_actions} remaining"
            )

        for index, node in enumerate(nodes):
            if node.task_name not in policy.allowed_tasks:
                return f"Node {index} task '{node.task_name}' is outside the session scope"
            if node.candidate_parameter not in policy.allowed_overrides:
                return (
                    f"Node {index} candidate '{node.candidate_parameter}' "
                    "is outside the session scope"
                )
            if node.reconfigure_before_task and not policy.allow_reconfigure:
                return f"Node {index} requests hardware reconfiguration outside the session scope"
            for name, value in node.parameter_overrides.items():
                bounds = policy.allowed_overrides.get(name)
                if bounds is None:
                    return f"Node {index} override '{name}' is outside the session scope"
                minimum = bounds.get("minimum")
                maximum = bounds.get("maximum")
                if minimum is not None and value < minimum:
                    return f"Node {index} override '{name}' is below the session minimum"
                if maximum is not None and value > maximum:
                    return f"Node {index} override '{name}' is above the session maximum"
        return None

    def run_campaign(
        self,
        *,
        session_id: str,
        qid: str,
        source_execution_id: str,
        nodes: list[AgentCampaignNode],
        max_pre_dispatch_retries: int = 1,
        max_node_executions: int | None = None,
        idempotency_prefix: str | None = None,
    ) -> AgentCampaignOutcome:
        """Run a bounded decision graph while preserving a fixed source snapshot."""
        if not nodes:
            raise ValueError("campaign requires at least one node")
        if max_pre_dispatch_retries < 0:
            raise ValueError("max_pre_dispatch_retries must be non-negative")
        execution_limit = len(nodes) if max_node_executions is None else max_node_executions
        if execution_limit <= 0:
            raise ValueError("max_node_executions must be positive")
        if idempotency_prefix is not None and (
            not idempotency_prefix or len(idempotency_prefix) > 96
        ):
            raise ValueError("idempotency_prefix must contain 1 to 96 characters")

        node_ids, graph_error = self._validate_graph(nodes)
        if graph_error is not None:
            return AgentCampaignOutcome(
                transition=AgentSkillTransition.HUMAN_ESCALATION,
                reason=graph_error,
                session_id=session_id,
                qid=qid,
                source_execution_id=source_execution_id,
                completed_nodes=0,
                attempts=0,
                outcomes=(),
            )
        node_indexes = {node_id: index for index, node_id in enumerate(node_ids)}

        try:
            session = self._client.get_agent_session(session_id)
        except QDashApiError as exc:
            step = _api_error_outcome(exc, session_id=session_id)
            return AgentCampaignOutcome(
                transition=step.transition,
                reason=step.reason,
                session_id=session_id,
                qid=qid,
                source_execution_id=source_execution_id,
                completed_nodes=0,
                attempts=0,
                outcomes=(),
            )

        policy_error = self._policy_error(session, qid, nodes, execution_limit)
        if policy_error is not None:
            return AgentCampaignOutcome(
                transition=AgentSkillTransition.HUMAN_ESCALATION,
                reason=policy_error,
                session_id=session_id,
                qid=qid,
                source_execution_id=source_execution_id,
                completed_nodes=0,
                attempts=0,
                outcomes=(),
            )

        prefix = idempotency_prefix or f"campaign-{uuid4()}"
        carried: dict[str, float] = {}
        outcomes: list[AgentStepOutcome] = []
        completed_nodes = 0
        node_path: list[str] = []
        visit_counts: dict[int, int] = {}
        current_index = 0

        while True:
            if len(node_path) >= execution_limit:
                return AgentCampaignOutcome(
                    transition=AgentSkillTransition.HUMAN_ESCALATION,
                    reason=f"Campaign reached the {execution_limit} node execution limit",
                    session_id=session_id,
                    qid=qid,
                    source_execution_id=source_execution_id,
                    completed_nodes=completed_nodes,
                    attempts=len(outcomes),
                    outcomes=tuple(outcomes),
                    carried_overrides=dict(carried),
                    node_path=tuple(node_path),
                )

            node = nodes[current_index]
            node_id = node_ids[current_index]
            visit = visit_counts.get(current_index, 0)
            visit_counts[current_index] = visit + 1
            node_path.append(node_id)
            overrides = {**carried, **node.parameter_overrides}
            retries = 0
            key_base = f"{prefix}-node-{current_index}"
            if visit:
                key_base = f"{key_base}-visit-{visit}"
            while True:
                outcome = self._step_runner.run_step(
                    session_id=session_id,
                    task_name=node.task_name,
                    qid=qid,
                    source_execution_id=source_execution_id,
                    candidate_parameter=node.candidate_parameter,
                    parameter_overrides=overrides,
                    diagnosis=node.diagnosis,
                    reconfigure_before_task=node.reconfigure_before_task,
                    commit_candidate=node.commit_candidate,
                    apply_backend=node.apply_backend,
                    push_to_github=node.push_to_github,
                    action_idempotency_key=f"{key_base}-action",
                    commit_idempotency_key=f"{key_base}-commit",
                    backend_apply_idempotency_key=f"{key_base}-apply",
                )
                outcomes.append(outcome)
                safe_to_retry = (
                    outcome.transition == AgentSkillTransition.RETRY
                    and outcome.operation_id is None
                    and outcome.execution_id is None
                    and outcome.candidate is None
                    and outcome.commit is None
                )
                if safe_to_retry and retries < max_pre_dispatch_retries:
                    retries += 1
                    continue
                break

            if outcome.transition not in {AgentSkillTransition.PASS, AgentSkillTransition.ROLLBACK}:
                return AgentCampaignOutcome(
                    transition=outcome.transition,
                    reason=(
                        f"Campaign stopped at node {current_index} "
                        f"({node.task_name}): {outcome.reason}"
                    ),
                    session_id=session_id,
                    qid=qid,
                    source_execution_id=source_execution_id,
                    completed_nodes=completed_nodes,
                    attempts=len(outcomes),
                    outcomes=tuple(outcomes),
                    carried_overrides=dict(carried),
                    node_path=tuple(node_path),
                )

            if outcome.transition == AgentSkillTransition.ROLLBACK:
                if node.on_rollback is None:
                    return AgentCampaignOutcome(
                        transition=outcome.transition,
                        reason=(
                            f"Campaign stopped at node {current_index} "
                            f"({node.task_name}): {outcome.reason}"
                        ),
                        session_id=session_id,
                        qid=qid,
                        source_execution_id=source_execution_id,
                        completed_nodes=completed_nodes,
                        attempts=len(outcomes),
                        outcomes=tuple(outcomes),
                        carried_overrides=dict(carried),
                        node_path=tuple(node_path),
                    )
                current_index = node_indexes[node.on_rollback]
                continue

            if outcome.candidate is None:
                return AgentCampaignOutcome(
                    transition=AgentSkillTransition.HUMAN_ESCALATION,
                    reason=(
                        f"Campaign node {current_index} passed without an authoritative candidate"
                    ),
                    session_id=session_id,
                    qid=qid,
                    source_execution_id=source_execution_id,
                    completed_nodes=completed_nodes,
                    attempts=len(outcomes),
                    outcomes=tuple(outcomes),
                    carried_overrides=dict(carried),
                    node_path=tuple(node_path),
                )
            carried[outcome.candidate.parameter_name] = outcome.candidate.value
            completed_nodes += 1

            if node.on_pass is not None:
                if node.on_pass == _CAMPAIGN_COMPLETE:
                    break
                current_index = node_indexes[node.on_pass]
                continue
            if current_index + 1 < len(nodes):
                current_index += 1
                continue
            break

        return AgentCampaignOutcome(
            transition=AgentSkillTransition.PASS,
            reason=f"Campaign completed {completed_nodes} nodes",
            session_id=session_id,
            qid=qid,
            source_execution_id=source_execution_id,
            completed_nodes=completed_nodes,
            attempts=len(outcomes),
            outcomes=tuple(outcomes),
            carried_overrides=dict(carried),
            node_path=tuple(node_path),
        )
