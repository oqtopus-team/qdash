"""Raw error text never reaches a durable intervention record or a resume outcome.

Every error below carries a fake credential marker. The intervention request (summary,
attempts, checkpoint) and the plan reason must not contain it, while the safe diagnostic
(the failed operation, the exception class, HTTP status, and the object ids) stays.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.client.services.agent_runner import (
    AgentCalibrationRunner,
    AgentInterventionReason,
    AgentPlanNode,
    AgentPlanResumeState,
    AgentPlanRunner,
    AgentSkillTransition,
    AgentStepOutcome,
    safe_error_reason,
)
from qdash.client.services.client_models import (
    AgentCandidateResponse,
    AgentInterventionResponse,
    AgentSessionResponse,
    CreateEvaluationRunResponse,
    EvaluationItem,
    EvaluationRunDetailResponse,
    EvaluationRunSummary,
    TaskNextAction,
)
from qdash.client.services.errors import (
    QDashAuthError,
    QDashTransportError,
    QDashValidationError,
)
from qdash.client.services.evaluation_planner import EvaluationPlanner

MARKER = "SYNTHETIC_SECRET_MARKER"
FAKE_TOKEN = "xoxb-FAKE-TOKEN-0000"  # noqa: S105 - synthetic marker, not a credential


def _session() -> AgentSessionResponse:
    return AgentSessionResponse.model_validate(
        {
            "session_id": "session-1",
            "project_id": "project-1",
            "chip_id": "chip-1",
            "status": "active",
            "created_by": "alice",
            "state_version": 0,
            "action_count": 0,
            "skill_name": "qubit-characterize",
            "skill_version": "1",
            "skill_hash": "sha256:test",
            "model_name": "local-model",
            "policy": {
                "qids": ["Q00"],
                "allowed_tasks": ["CheckRabi"],
                "allowed_actions": ["run_task"],
                "allowed_overrides": {"control_amplitude": {"minimum": 0.0, "maximum": 1.0}},
                "max_actions": 4,
                "autonomy": "auto",
            },
            "created_at": "2026-07-13T00:00:00Z",
            "updated_at": "2026-07-13T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        }
    )


def _candidate() -> AgentCandidateResponse:
    return AgentCandidateResponse(
        session_id="session-1",
        action_id="action-1",
        execution_id="execution-1",
        task_id="task-1",
        task_name="CheckRabi",
        qid="Q00",
        source_parameter_name="control_amplitude",
        parameter_name="control_amplitude",
        value=0.03,
        accepted=True,
        reason="passed",
    )


def _passed_step() -> AgentStepOutcome:
    return AgentStepOutcome(
        transition=AgentSkillTransition.PASS,
        reason="Candidate passed and remains staged",
        session_id="session-1",
        action_id="action-1",
        operation_id="operation-1",
        execution_id="execution-1",
        candidate=_candidate(),
    )


def _intervention() -> AgentInterventionResponse:
    return AgentInterventionResponse.model_validate(
        {
            "intervention_id": "intervention-1",
            "project_id": "project-1",
            "session_id": "session-1",
            "chip_id": "chip-1",
            "reason": "evaluation_failed",
            "summary": "stopped",
            "question": "resume?",
            "status": "open",
            "session_status": "waiting_for_human",
            "page_path": "/agent-sessions/session-1/interventions/intervention-1",
            "notification": {"status": "pending"},
            "created_at": "2026-07-13T00:00:05Z",
            "updated_at": "2026-07-13T00:00:05Z",
        }
    )


def _client() -> MagicMock:
    client = MagicMock()
    client.get_agent_session.return_value = _session()
    client.create_agent_intervention.return_value = _intervention()
    return client


NODES = [
    AgentPlanNode(node_id="rabi", task_name="CheckRabi", candidate_parameter="control_amplitude")
]


def _run(client: MagicMock, *, step_runner: Any = None, planner: Any = None, **kwargs: Any):
    runner = AgentPlanRunner(client, step_runner=step_runner, poll_interval_seconds=0)
    return runner.run_plan(
        session_id="session-1",
        qid="Q00",
        nodes=NODES,
        planner=planner,
        idempotency_prefix="plan-key",
        record_interventions=True,
        **kwargs,
    )


def _recorded(client: MagicMock) -> str:
    """Everything the runner sent to QDash for the intervention, as one string."""
    assert client.create_agent_intervention.called
    return json.dumps(
        [call.kwargs for call in client.create_agent_intervention.call_args_list], default=str
    )


def _assert_clean(outcome: Any, client: MagicMock) -> str:
    sent = _recorded(client)
    for text in (sent, outcome.reason):
        assert MARKER not in text
        assert FAKE_TOKEN not in text
    return sent


def _planner(evaluator: MagicMock) -> EvaluationPlanner:
    return EvaluationPlanner(
        evaluator,
        chip_id="chip-1",
        allowed_overrides={"control_amplitude": {"minimum": 0.0, "maximum": 1.0}},
        next_actions=lambda task_name: {"SUCCESS": TaskNextAction(action="continue")},
        poll_interval_seconds=0,
    )


def test_safe_error_reason_keeps_the_class_and_status_only() -> None:
    error = QDashTransportError(f"503 {MARKER} token={FAKE_TOKEN}", status_code=503)
    assert safe_error_reason("Reading X", error) == (
        "Reading X failed (QDashTransportError, HTTP 503)"
    )
    assert safe_error_reason("Reading X", RuntimeError(MARKER)) == (
        "Reading X failed (RuntimeError)"
    )


def test_thrown_evaluation_request_error_is_not_recorded() -> None:
    client = _client()
    steps = MagicMock()
    steps.run_step.side_effect = [_passed_step()]
    evaluator = MagicMock()
    evaluator.create_evaluation_run.side_effect = RuntimeError(f"{MARKER} {FAKE_TOKEN}")

    outcome = _run(client, step_runner=steps, planner=_planner(evaluator))

    assert outcome.escalation_reason == AgentInterventionReason.EVALUATION_FAILED
    sent = _assert_clean(outcome, client)
    kwargs = client.create_agent_intervention.call_args.kwargs
    assert kwargs["summary"] == (
        "Planner requested human review: Evaluating task result task-1 failed (RuntimeError)"
    )
    attempt = kwargs["attempts"][0]
    assert attempt["task_id"] == "task-1"
    assert attempt["action_id"] == "action-1"
    assert attempt["execution_id"] == "execution-1"
    assert "RuntimeError" in sent


def test_evaluator_backend_error_is_replaced_by_the_evaluation_ids() -> None:
    client = _client()
    steps = MagicMock()
    steps.run_step.side_effect = [_passed_step()]
    evaluator = MagicMock()
    evaluator.create_evaluation_run.return_value = CreateEvaluationRunResponse(
        run=EvaluationRunSummary(run_id="run-1", status="running"), task_ids=["task-1"]
    )
    evaluator.wait_for_evaluation_run.return_value = EvaluationRunDetailResponse(
        run=EvaluationRunSummary(run_id="run-1", status="completed"),
        evaluations=[
            EvaluationItem(
                evaluation_id="eval-1",
                run_id="run-1",
                task_id="task-1",
                task_name="CheckRabi",
                qid="Q00",
                status="failed",
                error=f"provider said Authorization: Bearer {FAKE_TOKEN} {MARKER}",
            )
        ],
    )

    outcome = _run(client, step_runner=steps, planner=_planner(evaluator))

    _assert_clean(outcome, client)
    kwargs = client.create_agent_intervention.call_args.kwargs
    assert (
        "Evaluation eval-1 of task result task-1 did not complete (status failed)"
        in (kwargs["summary"])
    )
    attempt = kwargs["attempts"][0]
    assert attempt["evaluation_id"] == "eval-1"
    assert attempt["evaluation_run_id"] == "run-1"
    assert attempt["status"] == "failed"


def test_unknown_skip_text_is_not_repeated() -> None:
    client = _client()
    steps = MagicMock()
    steps.run_step.side_effect = [_passed_step()]
    evaluator = MagicMock()
    evaluator.create_evaluation_run.return_value = CreateEvaluationRunResponse(
        run=EvaluationRunSummary(run_id="run-1", status="running"),
        task_ids=[],
        skipped={"task-1": MARKER},
    )

    outcome = _run(client, step_runner=steps, planner=_planner(evaluator))

    _assert_clean(outcome, client)
    assert "(reason not shown)" in outcome.reason
    assert "run-1" in outcome.reason


def test_a_failing_planner_callback_is_not_recorded() -> None:
    client = _client()
    steps = MagicMock()
    steps.run_step.side_effect = [_passed_step()]
    planner = MagicMock()
    planner.choose_next.side_effect = ValueError(f"{MARKER} {FAKE_TOKEN}")
    planner.export_history.return_value = {}

    outcome = _run(client, step_runner=steps, planner=planner)

    _assert_clean(outcome, client)
    assert outcome.reason == "The planner failed (ValueError)"
    assert outcome.escalation_reason == AgentInterventionReason.PLATFORM_ERROR


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            QDashTransportError(f"connection reset {MARKER}", status_code=None),
            "QDash API request failed (QDashTransportError)",
        ),
        (
            QDashValidationError(f"422 {MARKER}", status_code=422, payload={"detail": MARKER}),
            "QDash API request failed (QDashValidationError, HTTP 422)",
        ),
        (
            QDashAuthError(f"401 Bearer {FAKE_TOKEN}", status_code=401),
            "QDash API request failed (QDashAuthError, HTTP 401)",
        ),
    ],
)
def test_api_and_transport_errors_are_not_recorded(error: Exception, expected: str) -> None:
    client = _client()
    # The session read before the plan succeeds; the step's own requests fail.
    client.get_agent_session.side_effect = [_session(), _session(), error]
    client.submit_agent_action.side_effect = error

    outcome = _run(client, step_runner=None, max_pre_dispatch_retries=0)

    sent = _assert_clean(outcome, client)
    assert outcome.reason == f"Plan stopped at node 0 (CheckRabi): {expected}"
    assert client.create_agent_intervention.call_args.kwargs["attempts"][0]["reason"] == expected
    assert "QDash API request failed" in sent


def test_a_step_timeout_keeps_its_ids_but_not_its_text() -> None:
    client = _client()
    client.submit_agent_action.return_value = MagicMock(
        decision="authorized", action_id="action-1", execution_status="not_started"
    )
    client.execute_agent_action.return_value = MagicMock(execution_status="queued")
    client.wait_for_agent_action.side_effect = TimeoutError(f"timed out {MARKER}")
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    step = runner.run_step(
        session_id="session-1",
        task_name="CheckRabi",
        qid="Q00",
        candidate_parameter="control_amplitude",
    )

    assert step.reason == "Waiting for QDash failed (TimeoutError)"
    assert step.action_id == "action-1"


def test_a_backend_apply_error_is_referenced_by_its_commit() -> None:
    client = _client()
    client.submit_agent_action.return_value = MagicMock(
        decision="authorized", action_id="action-1", execution_status="not_started"
    )
    dispatched = MagicMock(
        execution_status="completed", operation_id="operation-1", execution_id="execution-1"
    )
    client.execute_agent_action.return_value = dispatched
    client.wait_for_agent_action.return_value = dispatched
    client.wait_for_agent_action_execution.return_value = dispatched
    client.wait_for_execution.return_value = MagicMock(status="completed")
    client.list_agent_action_candidates.return_value = [_candidate()]
    committed = MagicMock(
        commit_id="commit-1",
        backend_status="failed",
        backend_verified=False,
        backend_error=f"git push https://{FAKE_TOKEN}@example.invalid {MARKER}",
    )
    client.commit_agent_action_candidate.return_value = committed
    client.apply_agent_candidate_commit.return_value = committed
    client.wait_for_agent_candidate_apply.return_value = committed
    runner = AgentCalibrationRunner(client, poll_interval_seconds=0)

    step = runner.run_step(
        session_id="session-1",
        task_name="CheckRabi",
        qid="Q00",
        candidate_parameter="control_amplitude",
        commit_candidate=True,
        apply_backend=True,
    )

    assert step.transition == AgentSkillTransition.HUMAN_ESCALATION
    assert MARKER not in step.reason
    assert FAKE_TOKEN not in step.reason
    assert step.reason == "Backend application of commit commit-1 ended failed and was not verified"


def test_a_failed_candidate_reread_on_resume_is_not_recorded() -> None:
    client = _client()
    client.list_agent_action_candidates.side_effect = QDashTransportError(MARKER, status_code=502)
    resume = AgentPlanResumeState(
        intervention_id="intervention-0",
        start_node_id="rabi",
        node_path=("rabi",),
        visit_counts={"rabi": 1},
        accepted_candidates=(
            {"action_id": "action-1", "parameter_name": "control_amplitude", "task_id": "task-1"},
        ),
        planner_history={},
    )

    outcome = _run(client, resume=resume, max_node_executions=3)

    _assert_clean(outcome, client)
    assert outcome.reason == (
        "Re-reading candidate control_amplitude from action action-1 failed "
        "(QDashTransportError, HTTP 502)"
    )
