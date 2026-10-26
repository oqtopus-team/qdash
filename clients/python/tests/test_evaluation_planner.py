"""The evaluation planner follows the task knowledge's next_actions table and nothing else."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from qdash.client.services.agent_runner import (
    PLAN_DEFAULT,
    PLAN_ESCALATE,
    AgentPlannerObservation,
    AgentSkillTransition,
    AgentStepOutcome,
)
from qdash.client.services.evaluation_planner import (
    EvaluationPlanner,
    parse_suggested_range,
    verdict_from_diagnosis,
)
from qdash.client.services.models import (
    AgentCandidateResponse,
    CreateEvaluationRunResponse,
    EvaluationItem,
    EvaluationOutput,
    EvaluationRunDetailResponse,
    EvaluationRunSummary,
    TaskNextAction,
)

BOUNDS = {"control_amplitude": {"minimum": 0.01, "maximum": 0.05}}
TABLE = {
    "SUCCESS": TaskNextAction(action="continue"),
    "SUBOPTIMAL": TaskNextAction(action="retry", suggested_range_parameter="control_amplitude"),
    "FREQUENCY_MISMATCH": TaskNextAction(action="retry", overrides={"control_amplitude": 0.02}),
    "NO_SIGNAL": TaskNextAction(action="run_task", task="CheckChevron", note="find the frequency"),
    "ANOMALOUS": TaskNextAction(action="request_human", note="inspect the figure"),
}


def _candidate(*, task_id: str = "task-1", accepted: bool = True) -> AgentCandidateResponse:
    return AgentCandidateResponse(
        session_id="session-1",
        action_id="action-1",
        execution_id="execution-1",
        task_id=task_id,
        task_name="CheckRabi",
        qid="Q00",
        source_parameter_name="control_amplitude",
        parameter_name="control_amplitude",
        value=0.03,
        accepted=accepted,
        reason="passed" if accepted else "rejected",
    )


def _observation(
    *,
    transition: AgentSkillTransition = AgentSkillTransition.PASS,
    candidate: AgentCandidateResponse | None = None,
    node_visits: dict[str, int] | None = None,
) -> AgentPlannerObservation:
    outcome = AgentStepOutcome(
        transition=transition,
        reason="step result",
        session_id="session-1",
        execution_id="execution-1",
        candidate=candidate,
    )
    return AgentPlannerObservation(
        session_id="session-1",
        qid="Q00",
        source_execution_id=None,
        last_node_id="rabi",
        last_outcome=outcome,
        node_path=("rabi",),
        carried_overrides={},
        available_node_ids=("rabi", "chevron", "configure"),
        remaining_node_executions=5,
        node_tasks={"rabi": "CheckRabi", "chevron": "CheckChevron", "configure": "Configure"},
        node_visits=node_visits or {"rabi": 1, "chevron": 0, "configure": 0},
    )


def _client(diagnoses: list[dict[str, Any]], *, status: str = "completed") -> MagicMock:
    client = MagicMock()
    client.create_evaluation_run.return_value = CreateEvaluationRunResponse(
        run=EvaluationRunSummary(run_id="run-1", status="running"), task_ids=["task-1"]
    )
    client.wait_for_evaluation_run.side_effect = [
        EvaluationRunDetailResponse(
            run=EvaluationRunSummary(run_id="run-1", status="completed"),
            evaluations=[
                EvaluationItem(
                    evaluation_id=f"eval-{index}",
                    run_id="run-1",
                    task_id="task-1",
                    task_name="CheckRabi",
                    qid="Q00",
                    status=status,
                    error=None if status == "completed" else "model unavailable",
                    output=EvaluationOutput(diagnosis=diagnosis) if status == "completed" else None,
                )
            ],
        )
        for index, diagnosis in enumerate(diagnoses)
    ]
    return client


def _diagnosis(status: str, *, suggested: object = "N/A", fit: str = "reliable") -> dict[str, Any]:
    return {
        "calibration_diagnosis": {"status": status, "suggested_range": suggested, "notes": "n"},
        "fit_reliability": {"assessment": fit, "reason": "r"},
    }


def _planner(client: MagicMock, **kwargs: Any) -> EvaluationPlanner:
    return EvaluationPlanner(
        client,
        chip_id="chip-1",
        allowed_overrides=BOUNDS,
        next_actions=lambda task_name: TABLE,
        **kwargs,
    )


# ------------------------------------------------------------------ parsing


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("(0.02, 0.04)", (0.02, 0.04)),
        ("0.02 to 0.04 a.u.", (0.02, 0.04)),
        ([1, 2.5], (1.0, 2.5)),
        ("N/A", None),
        ("(5, 1)", None),
        (None, None),
        ("(1, 2, 3)", None),
    ],
)
def test_parse_suggested_range(value: object, expected: tuple[float, float] | None) -> None:
    assert parse_suggested_range(value) == expected


def test_verdict_reads_status_fit_and_range() -> None:
    verdict = verdict_from_diagnosis("eval-1", _diagnosis("suboptimal", suggested="(0.02, 0.04)"))
    assert verdict.status == "SUBOPTIMAL"
    assert verdict.suggested_range == (0.02, 0.04)
    assert verdict.fit_reliability == "reliable"
    with pytest.raises(ValueError, match="status question"):
        verdict_from_diagnosis("eval-1", {"fit_reliability": {"assessment": "reliable"}})


# ------------------------------------------------------------------ decisions


def test_success_follows_the_plan() -> None:
    client = _client([_diagnosis("SUCCESS")])
    planner = _planner(client)

    decision = planner.choose_next(_observation(candidate=_candidate()))

    assert decision.target_node_id == PLAN_DEFAULT
    assert "eval-0: SUCCESS" in decision.reason
    client.create_evaluation_run.assert_called_once_with(
        chip_id="chip-1", task="CheckRabi", task_ids=["task-1"], trigger="single"
    )
    assert planner.traces[0].verdict is not None
    assert planner.traces[0].verdict.status == "SUCCESS"


def test_success_after_rollback_cannot_continue() -> None:
    planner = _planner(_client([_diagnosis("SUCCESS")]))
    decision = planner.choose_next(
        _observation(transition=AgentSkillTransition.ROLLBACK, candidate=_candidate(accepted=False))
    )
    assert decision.target_node_id == PLAN_ESCALATE
    assert "did not pass" in decision.reason


def test_retry_takes_the_midpoint_of_the_suggested_range_within_bounds() -> None:
    planner = _planner(_client([_diagnosis("SUBOPTIMAL", suggested="(0.02, 0.04)")]))

    decision = planner.choose_next(_observation(candidate=_candidate()))

    assert decision.target_node_id == "rabi"
    assert decision.parameter_overrides == {"control_amplitude": pytest.approx(0.03)}


def test_retry_escalates_when_the_range_leaves_the_session_bounds() -> None:
    planner = _planner(_client([_diagnosis("SUBOPTIMAL", suggested="(0.08, 0.12)")]))
    decision = planner.choose_next(_observation(candidate=_candidate()))
    assert decision.target_node_id == PLAN_ESCALATE
    assert "above the session maximum" in decision.reason


def test_retry_escalates_without_a_suggested_range() -> None:
    planner = _planner(_client([_diagnosis("SUBOPTIMAL")]))
    decision = planner.choose_next(_observation(candidate=_candidate()))
    assert decision.target_node_id == PLAN_ESCALATE
    assert "no suggested range" in decision.reason


def test_retry_with_static_overrides() -> None:
    planner = _planner(_client([_diagnosis("FREQUENCY_MISMATCH")]))
    decision = planner.choose_next(_observation(candidate=_candidate()))
    assert decision.target_node_id == "rabi"
    assert decision.parameter_overrides == {"control_amplitude": 0.02}


def test_run_task_targets_the_node_that_runs_the_task() -> None:
    planner = _planner(_client([_diagnosis("NO_SIGNAL")]))
    decision = planner.choose_next(_observation(candidate=_candidate()))
    assert decision.target_node_id == "chevron"
    assert decision.parameter_overrides == {}
    assert "find the frequency" in decision.reason


def test_run_task_outside_the_plan_escalates() -> None:
    planner = EvaluationPlanner(
        _client([_diagnosis("NO_SIGNAL")]),
        chip_id="chip-1",
        allowed_overrides=BOUNDS,
        next_actions=lambda _: {"NO_SIGNAL": TaskNextAction(action="run_task", task="CheckT1")},
    )
    decision = planner.choose_next(_observation(candidate=_candidate()))
    assert decision.target_node_id == PLAN_ESCALATE
    assert "'CheckT1' is not a node" in decision.reason


def test_request_human_and_unknown_status_escalate() -> None:
    planner = _planner(_client([_diagnosis("ANOMALOUS"), _diagnosis("BEATING_PATTERN")]))
    first = planner.choose_next(_observation(candidate=_candidate()))
    assert first.target_node_id == PLAN_ESCALATE
    assert "inspect the figure" in first.reason
    second = planner.choose_next(_observation(candidate=_candidate()))
    assert second.target_node_id == PLAN_ESCALATE
    assert "BEATING_PATTERN, which has no next action" in second.reason


def test_round_budget_stops_a_retry() -> None:
    planner = _planner(_client([_diagnosis("SUBOPTIMAL", suggested="(0.02, 0.04)")]))
    decision = planner.choose_next(
        _observation(candidate=_candidate(), node_visits={"rabi": 3, "chevron": 0, "configure": 0})
    )
    assert decision.target_node_id == PLAN_ESCALATE
    assert "already ran 3 times (limit 3)" in decision.reason


def test_repeated_status_stops_the_plan() -> None:
    planner = _planner(
        _client([_diagnosis("SUBOPTIMAL", suggested="(0.02, 0.04)")] * 3),
        max_rounds_per_target=10,
    )
    decisions = [
        planner.choose_next(
            _observation(
                candidate=_candidate(), node_visits={"rabi": n, "chevron": 0, "configure": 0}
            )
        )
        for n in (1, 2, 3)
    ]
    assert [d.target_node_id for d in decisions[:2]] == ["rabi", "rabi"]
    assert decisions[2].target_node_id == PLAN_ESCALATE
    assert "came back 3 times" in decisions[2].reason


def test_unreliable_fits_stop_the_plan() -> None:
    planner = _planner(
        _client(
            [
                _diagnosis("SUBOPTIMAL", suggested="(0.02, 0.04)", fit="unreliable"),
                _diagnosis("SUCCESS", fit="unreliable"),
            ]
        )
    )
    first = planner.choose_next(_observation(candidate=_candidate()))
    assert first.target_node_id == "rabi"
    second = planner.choose_next(_observation(candidate=_candidate()))
    assert second.target_node_id == PLAN_ESCALATE
    assert "unreliable 2 times" in second.reason


def test_missing_task_result_escalates_without_evaluating() -> None:
    client = _client([])
    planner = _planner(client)
    decision = planner.choose_next(_observation(candidate=None))
    assert decision.target_node_id == PLAN_ESCALATE
    client.create_evaluation_run.assert_not_called()


def test_incomplete_evaluation_raises_for_the_runner_to_escalate() -> None:
    planner = _planner(_client([_diagnosis("SUCCESS")], status="failed"))
    with pytest.raises(RuntimeError, match="did not complete"):
        planner.choose_next(_observation(candidate=_candidate()))


def test_skipped_task_result_raises() -> None:
    client = _client([_diagnosis("SUCCESS")])
    client.create_evaluation_run.return_value = CreateEvaluationRunResponse(
        run=EvaluationRunSummary(run_id="run-1", status="completed"),
        skipped={"task-1": "no figure"},
    )
    with pytest.raises(RuntimeError, match="no figure"):
        _planner(client).choose_next(_observation(candidate=_candidate()))
