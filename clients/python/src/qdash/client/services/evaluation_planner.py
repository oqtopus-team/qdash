"""Choose a plan's next node from the calibration evaluation of its last result.

An autonomous plan runs inside an agent session whose policy allows
``autonomy: auto``. After each node the planner asks QDash to evaluate the
node's task result with the calibration-evaluation model (the QCalEval
questions), reads the status the model chose, and looks that status up in the
task's ``next_actions`` table from the task knowledge. The table, the session's
override bounds, and the round budget decide the next node; the planner never
invents a step, a parameter value, or a task outside the pre-authorized plan.

Anything the table does not cover stops the plan for a person: an unknown
status, a status without an entry, an evaluation that did not complete, a
suggested range the session bounds do not allow, or a round budget that ran out.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qdash.client.services.agent_runner import (
    PLAN_DEFAULT,
    PLAN_ESCALATE,
    AgentPlannerDecision,
    AgentSkillTransition,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from qdash.client.services.agent_runner import AgentPlannerObservation
    from qdash.client.services.client import QDashClient
    from qdash.client.services.models import TaskNextAction

_RANGE_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class EvaluationVerdict:
    """What the planner read from one completed evaluation."""

    evaluation_id: str
    status: str
    suggested_range: tuple[float, float] | None = None
    fit_reliability: str | None = None
    notes: str = ""


@dataclass
class EvaluationPlannerTrace:
    """Audit of one planner decision, kept on the planner for the caller."""

    node_id: str
    task_id: str
    verdict: EvaluationVerdict | None
    decision: AgentPlannerDecision
    history: list[EvaluationVerdict] = field(default_factory=list)


def parse_suggested_range(value: object) -> tuple[float, float] | None:
    """The (low, high) pair of a suggested range, written as a list or as text."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            low, high = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    elif isinstance(value, str):
        numbers = _RANGE_NUMBER_RE.findall(value)
        if len(numbers) != 2:
            return None
        low, high = float(numbers[0]), float(numbers[1])
    else:
        return None
    if not (math.isfinite(low) and math.isfinite(high)) or low > high:
        return None
    return low, high


def verdict_from_diagnosis(evaluation_id: str, diagnosis: Mapping[str, Any]) -> EvaluationVerdict:
    """Read the status question's answer (and the fit question's) from a diagnosis."""
    status_answer = diagnosis.get("calibration_diagnosis")
    if not isinstance(status_answer, Mapping) or not status_answer.get("status"):
        raise ValueError("the evaluation did not answer the status question")
    fit_answer = diagnosis.get("fit_reliability")
    fit = fit_answer.get("assessment") if isinstance(fit_answer, Mapping) else None
    return EvaluationVerdict(
        evaluation_id=evaluation_id,
        status=str(status_answer["status"]).strip().upper(),
        suggested_range=parse_suggested_range(status_answer.get("suggested_range")),
        fit_reliability=str(fit).strip().lower() if fit else None,
        notes=str(status_answer.get("notes") or ""),
    )


class EvaluationPlanner:
    """``AgentPlanner`` that follows the task knowledge's ``next_actions``."""

    def __init__(
        self,
        client: QDashClient,
        *,
        chip_id: str,
        allowed_overrides: Mapping[str, Mapping[str, float | None]],
        max_rounds_per_target: int = 3,
        next_actions: Callable[[str], Mapping[str, TaskNextAction]] | None = None,
        evaluation_timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 2.0,
        max_repeated_status: int = 3,
        max_unreliable_fits: int = 2,
    ) -> None:
        if max_rounds_per_target < 1:
            raise ValueError("max_rounds_per_target must be positive")
        if max_repeated_status < 1 or max_unreliable_fits < 1:
            raise ValueError("stop thresholds must be positive")
        self._client = client
        self._chip_id = chip_id
        self._allowed_overrides = {name: dict(bounds) for name, bounds in allowed_overrides.items()}
        self._max_rounds = max_rounds_per_target
        self._next_actions = next_actions or client.get_task_next_actions
        self._timeout = evaluation_timeout_seconds
        self._poll = poll_interval_seconds
        self._max_repeated_status = max_repeated_status
        self._max_unreliable_fits = max_unreliable_fits
        self._tables: dict[str, Mapping[str, TaskNextAction]] = {}
        self._history: dict[str, list[EvaluationVerdict]] = {}
        self.traces: list[EvaluationPlannerTrace] = []

    @property
    def max_rounds_per_target(self) -> int:
        """How many times one node may run on the target before the planner escalates."""
        return self._max_rounds

    # ------------------------------------------------------------------ planner

    def choose_next(self, observation: AgentPlannerObservation) -> AgentPlannerDecision:
        outcome = observation.last_outcome
        candidate = outcome.candidate
        if candidate is None or not candidate.task_id:
            return self._escalate(
                observation, None, None, "the last node left no task result to evaluate"
            )
        task_id = candidate.task_id
        task_name = candidate.task_name
        verdict = self._evaluate(task_id, task_name)
        history = self._history.setdefault(observation.last_node_id, [])
        history.append(verdict)

        stop = self._stop_reason(history)
        if stop is not None:
            return self._escalate(observation, task_id, verdict, stop)

        table = self._table(task_name)
        action = table.get(verdict.status)
        if action is None:
            offered = ", ".join(sorted(table)) or "none"
            return self._escalate(
                observation,
                task_id,
                verdict,
                f"{task_name} evaluation reported {verdict.status}, which has no next action "
                f"(table covers {offered})",
            )
        reason = f"{task_name} evaluation {verdict.evaluation_id}: {verdict.status}"
        if action.note:
            reason = f"{reason}; {action.note}"

        if action.action == "request_human":
            return self._escalate(observation, task_id, verdict, reason)
        if action.action == "continue":
            if outcome.transition != AgentSkillTransition.PASS:
                return self._escalate(
                    observation,
                    task_id,
                    verdict,
                    f"{reason}; the node did not pass, so the plan cannot continue",
                )
            return self._record(
                observation, task_id, verdict, AgentPlannerDecision(PLAN_DEFAULT, reason)
            )

        if action.action == "retry":
            target = observation.last_node_id
        else:  # run_task
            node_for_task = self._node_for_task(observation, action.task or "")
            if node_for_task is None:
                return self._escalate(
                    observation,
                    task_id,
                    verdict,
                    f"{reason}; task {action.task!r} is not a node of this plan",
                )
            target = node_for_task
        visits = observation.node_visits.get(target, 0)
        if visits >= self._max_rounds:
            return self._escalate(
                observation,
                task_id,
                verdict,
                f"{reason}; node {target!r} already ran {visits} times (limit {self._max_rounds})",
            )

        overrides = dict(action.overrides)
        if action.suggested_range_parameter:
            if verdict.suggested_range is None:
                return self._escalate(
                    observation,
                    task_id,
                    verdict,
                    f"{reason}; the evaluation gave no suggested range",
                )
            low, high = verdict.suggested_range
            overrides[action.suggested_range_parameter] = (low + high) / 2
        bounded, bound_error = self._within_bounds(overrides)
        if bound_error is not None:
            return self._escalate(observation, task_id, verdict, f"{reason}; {bound_error}")
        return self._record(
            observation,
            task_id,
            verdict,
            AgentPlannerDecision(target, reason, parameter_overrides=bounded),
        )

    # ------------------------------------------------------------------ helpers

    def _evaluate(self, task_id: str, task_name: str) -> EvaluationVerdict:
        """Request an evaluation of one task result and wait for its verdict."""
        created = self._client.create_evaluation_run(
            chip_id=self._chip_id, task=task_name, task_ids=[task_id], trigger="single"
        )
        if task_id in created.skipped:
            raise RuntimeError(
                f"task result {task_id} was not evaluated: {created.skipped[task_id]}"
            )
        detail = self._client.wait_for_evaluation_run(
            created.run.run_id,
            timeout_seconds=self._timeout,
            poll_interval_seconds=self._poll,
        )
        item = next((e for e in detail.evaluations if e.task_id == task_id), None)
        if item is None:
            raise RuntimeError(f"evaluation run {created.run.run_id} holds no result for {task_id}")
        if item.status != "completed" or item.output is None or not item.output.diagnosis:
            raise RuntimeError(
                f"evaluation {item.evaluation_id} did not complete ({item.status}): {item.error or ''}".strip()
            )
        return verdict_from_diagnosis(item.evaluation_id, item.output.diagnosis)

    def _table(self, task_name: str) -> Mapping[str, TaskNextAction]:
        if task_name not in self._tables:
            self._tables[task_name] = {
                code.upper(): action for code, action in self._next_actions(task_name).items()
            }
        return self._tables[task_name]

    def _stop_reason(self, history: list[EvaluationVerdict]) -> str | None:
        statuses = [verdict.status for verdict in history]
        if len(statuses) >= self._max_repeated_status and (
            len(set(statuses[-self._max_repeated_status :])) == 1
        ):
            return f"the same status {statuses[-1]} came back {self._max_repeated_status} times"
        unreliable = Counter(
            verdict.fit_reliability == "unreliable"
            for verdict in history[-self._max_unreliable_fits :]
        )
        if unreliable[True] >= self._max_unreliable_fits:
            return f"the fit was unreliable {self._max_unreliable_fits} times in a row"
        return None

    @staticmethod
    def _node_for_task(observation: AgentPlannerObservation, task_name: str) -> str | None:
        return next(
            (node_id for node_id, name in observation.node_tasks.items() if name == task_name), None
        )

    def _within_bounds(self, overrides: dict[str, float]) -> tuple[dict[str, float], str | None]:
        bounded: dict[str, float] = {}
        for name, value in overrides.items():
            bounds = self._allowed_overrides.get(name)
            if bounds is None:
                return {}, f"override {name!r} is outside the session scope"
            if not math.isfinite(value):
                return {}, f"override {name!r} is not finite"
            minimum, maximum = bounds.get("minimum"), bounds.get("maximum")
            if minimum is not None and value < minimum:
                return {}, f"override {name!r}={value:g} is below the session minimum {minimum:g}"
            if maximum is not None and value > maximum:
                return {}, f"override {name!r}={value:g} is above the session maximum {maximum:g}"
            bounded[name] = value
        return bounded, None

    def _escalate(
        self,
        observation: AgentPlannerObservation,
        task_id: str | None,
        verdict: EvaluationVerdict | None,
        reason: str,
    ) -> AgentPlannerDecision:
        return self._record(
            observation, task_id, verdict, AgentPlannerDecision(PLAN_ESCALATE, reason)
        )

    def _record(
        self,
        observation: AgentPlannerObservation,
        task_id: str | None,
        verdict: EvaluationVerdict | None,
        decision: AgentPlannerDecision,
    ) -> AgentPlannerDecision:
        self.traces.append(
            EvaluationPlannerTrace(
                node_id=observation.last_node_id,
                task_id=task_id or "",
                verdict=verdict,
                decision=decision,
                history=list(self._history.get(observation.last_node_id, [])),
            )
        )
        return decision
