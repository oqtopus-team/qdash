"""Turn the literal plan of a saved flow into the execution dialog's preview.

Manual rounds are checked here with the same functions the worker runs before
any target measures; automatic modes are described, never computed, because
their groups depend on run-time state (filters, candidates, calibration data).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.api.schemas.flow import (
    ExecutionPlanIssue,
    ExecutionPlanRound,
    ExecutionPlanRun,
    ExecutionPlanStep,
    FlowExecutionPlanResponse,
)
from qdash.api.services.flow_service.execution_plan import (
    ONE_QUBIT_MODE_STEPS,
    TWO_QUBIT_MODE_STEPS,
    StaticPlan,
    StaticStep,
    resolve_execution_plan,
)
from qdash.api.services.manual_round_checks import ChipRoundModel, RoundCheck, check_rounds
from qdash.common.manual_rounds import (
    MANUAL_TARGET_OVERRIDE_REASON,
    ManualRoundsError,
    PairRounds,
    QubitRounds,
    RoundIssue,
    mux_target_qids,
    pair_rounds_for_mode,
    qubit_rounds_for_mode,
)
from qdash.datamodel.calibration_pipeline import STEP_CATALOG
from qdash.datamodel.one_qubit_execution_mode import validate_one_qubit_step_execution_mode
from qdash.datamodel.two_qubit_execution_mode import (
    DEFAULT_MAX_PARALLEL_OPS,
    validate_two_qubit_execution_mode,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from qdash.datamodel.flow_targets import FlowTargetOverride

_ROUND_WAIT = (
    "the next round starts after every {target} of the round has finished. A round is not a "
    "per-task barrier and does not align pulse timing."
)

_AUTOMATIC_SUMMARIES = {
    "parallel_by_round": (
        "The scheduler forms rounds of qubits from different MUXes at run time; every qubit of "
        "a round finishes before the next round starts."
    ),
    "parallel_by_mux": (
        "MUXes run in parallel within the scheduler's box stages; the qubits of one MUX run one "
        "after another, and each MUX starts its next qubit as soon as the previous one finishes."
    ),
    "sequential": "One MUX and one qubit at a time.",
    "simultaneous_spectroscopy": (
        "Experimental: each supported spectroscopy call measures a batch of qubits at once."
    ),
}

_OTHER_SUMMARIES = {
    "ConfigureAll": "Configures every box of the targeted MUXes once.",
    "FilterByStatus": "Keeps the qubits whose referenced step succeeded, at run time.",
    "FilterByMetric": "Keeps the qubits whose metric meets the threshold, at run time.",
}

# Where the pairs of an automatic two-qubit step or GenerateCRSchedule come from,
# by the run's target class; None when the source does not state the class.
_PAIR_SOURCES: dict[str | None, str] = {
    "CouplingTargets": (
        "groups exactly the listed directed pairs of the targets whose qubits are still "
        "candidates; no pair is added or reversed"
    ),
    "MuxTargets": "picks the pairs among the candidate qubits and groups them",
    "QubitTargets": "picks the pairs among the candidate qubits and groups them",
    None: (
        "groups the listed pairs of CouplingTargets, or picks pairs among the candidate qubits "
        "for other targets"
    ),
}

_GROUP_LIMITS = (
    "Groups avoid shared qubits, MUXes and modeled modules and hold at most {cap} pairs "
    "(max_parallel_ops)."
)


def _pair_source(target_type: str | None) -> str:
    return _PAIR_SOURCES.get(target_type) or _PAIR_SOURCES[None]


def _generate_summary(step: StaticStep, target_type: str | None) -> str:
    cap = step.max_parallel_ops or DEFAULT_MAX_PARALLEL_OPS
    return (
        f"At run time the CR scheduler {_pair_source(target_type)}, for later automatic "
        f"two-qubit steps. " + _GROUP_LIMITS.format(cap=cap)
    )


def _automatic_pair_summary(step: StaticStep, target_type: str | None, after_generate: bool) -> str:
    if after_generate:
        return (
            "Runs the groups of the earlier GenerateCRSchedule. Pairs whose qubits a filter "
            "removed since are left out; the remaining groups are not regrouped."
        )
    cap = step.max_parallel_ops or DEFAULT_MAX_PARALLEL_OPS
    return f"At run time the CR scheduler {_pair_source(target_type)}. " + _GROUP_LIMITS.format(
        cap=cap
    )


def _issue(issue: RoundIssue) -> ExecutionPlanIssue:
    return ExecutionPlanIssue(
        round=issue.round_number, targets=list(issue.targets), message=issue.reason
    )


def _target_qids(
    targets: FlowTargetOverride | None, model: Callable[[], ChipRoundModel]
) -> list[str] | None:
    """The qubits a run starts from, when the source states them literally."""
    if targets is None:
        return None
    if targets.qids is not None:
        return list(targets.qids)
    if targets.coupling_pairs is not None:
        return list(dict.fromkeys(qid for pair in targets.coupling_pairs for qid in pair))
    loaded = model()
    if loaded.wiring is None or loaded.mapping_error is not None or targets.mux_ids is None:
        return None
    return mux_target_qids(targets.mux_ids, targets.exclude_qids, loaded.wiring, loaded.mux_mapping)


def _parse_rounds(step: StaticStep) -> tuple[QubitRounds | PairRounds | None, list[RoundIssue]]:
    """Rounds of a step, parsed as the step class parses them."""
    mode = step.execution_mode or ""
    try:
        if step.type in TWO_QUBIT_MODE_STEPS:
            validate_two_qubit_execution_mode(mode)
            cap = (step.max_parallel_ops or 1) if step.max_parallel_ops_set else None
            return pair_rounds_for_mode(mode, step.rounds, cap, step=step.name), []
        validate_one_qubit_step_execution_mode(mode)
        return qubit_rounds_for_mode(mode, step.rounds, step=step.name), []
    except ManualRoundsError as exc:
        return None, exc.issues
    except ValueError as exc:
        return None, [RoundIssue(str(exc))]


def _round_targets(round_: tuple[Any, ...]) -> list[str]:
    return [target if isinstance(target, str) else f"{target[0]}-{target[1]}" for target in round_]


def _plan_step(
    index: int,
    step: StaticStep,
    candidates: list[str] | None,
    model: Callable[[], ChipRoundModel],
    *,
    target_type: str | None = None,
    after_generate: bool = False,
) -> ExecutionPlanStep:
    entry = STEP_CATALOG.get(step.type)
    scope = (entry.task_scope if entry is not None else None) or "none"
    base: dict[str, Any] = {
        "index": index,
        "type": step.type,
        "name": step.name,
        "scope": scope,
        "execution_mode": step.execution_mode,
        "tasks": list(step.tasks) if step.tasks is not None else None,
    }
    if step.type not in ONE_QUBIT_MODE_STEPS | TWO_QUBIT_MODE_STEPS:
        mode_summary = _AUTOMATIC_SUMMARIES.get(step.execution_mode or "")
        if step.type == "GenerateCRSchedule":
            summary = _generate_summary(step, target_type)
        else:
            summary = _OTHER_SUMMARIES.get(step.type) or (
                f"Scheduled automatically at run time. {mode_summary}" if mode_summary else ""
            )
        return ExecutionPlanStep(
            **base,
            schedule="automatic" if step.type == "BringUp" else "none",
            summary=summary or "Runs at run time.",
        )

    rounds, issues = _parse_rounds(step)
    if step.execution_mode != "manual" or rounds is None:
        if step.type in TWO_QUBIT_MODE_STEPS:
            summary = _automatic_pair_summary(step, target_type, after_generate)
        else:
            summary = _AUTOMATIC_SUMMARIES.get(step.execution_mode or "", "")
        return ExecutionPlanStep(
            **base,
            schedule="manual" if step.execution_mode == "manual" else "automatic",
            summary=summary or "Rounds could not be read.",
            issues=[_issue(issue) for issue in issues],
        )

    pair_scope = step.type in TWO_QUBIT_MODE_STEPS
    check: RoundCheck = check_rounds(
        "coupling" if pair_scope else "qubit", rounds, model(), candidates
    )
    target = "pair" if pair_scope else "qubit"
    return ExecutionPlanStep(
        **base,
        schedule="manual",
        rounds=[
            ExecutionPlanRound(number=number, targets=_round_targets(round_))
            for number, round_ in enumerate(rounds, start=1)
        ],
        summary=(
            f"Runs {len(rounds)} round{'s' if len(rounds) != 1 else ''} in the order written. "
            f"The {target}s of a round run in parallel, each running the full task list; "
            + _ROUND_WAIT.format(target=target)
        ),
        issues=[_issue(issue) for issue in check.issues],
        unchecked=list(check.unchecked),
    )


def build_execution_plan(
    *,
    flow_name: str,
    chip_id: str,
    updated_at: datetime,
    code: str,
    function_name: str,
    parameters: dict[str, Any],
    chip_model: Callable[[], ChipRoundModel],
) -> FlowExecutionPlanResponse:
    """The preview of one saved source for one chip. Reads only files and the database."""
    cached: list[ChipRoundModel] = []

    def model() -> ChipRoundModel:
        if not cached:
            cached.append(chip_model())
        return cached[0]

    static: StaticPlan = resolve_execution_plan(code, function_name, parameters)
    has_manual = bool(static.manual_steps)
    runs: list[ExecutionPlanRun] = []
    top_issues: list[ExecutionPlanIssue] = []
    if static.resolved:
        for run in static.runs:
            initial = (
                _target_qids(run.targets, model)
                if any(step.execution_mode == "manual" for step in run.steps)
                else None
            )
            selection_changed = False
            generated = False
            steps: list[ExecutionPlanStep] = []
            for index, step in enumerate(run.steps, start=1):
                # OneQubitCheck always runs on the run's targets; other steps read
                # the candidates, which a filter replaces at run time.
                known = step.type == "OneQubitCheck" or not selection_changed
                steps.append(
                    _plan_step(
                        index,
                        step,
                        initial if known else None,
                        model,
                        target_type=run.target_type,
                        after_generate=generated,
                    )
                )
                if step.type in {"FilterByStatus", "FilterByMetric"}:
                    selection_changed = True
                generated = generated or step.type == "GenerateCRSchedule"
            runs.append(ExecutionPlanRun(targets=run.targets, steps=steps))
    else:
        for step in static.manual_steps:
            if not step.literal:
                # Rounds built from run-time values are checked by the worker.
                continue
            checked = _plan_step(0, step, None, model)
            top_issues.extend(
                ExecutionPlanIssue(
                    round=issue.round,
                    targets=issue.targets,
                    message=f"{step.name}: {issue.message}",
                )
                for issue in checked.issues
            )
    invalid = bool(top_issues) or any(step.issues for run in runs for step in run.steps)
    return FlowExecutionPlanResponse(
        flow_name=flow_name,
        chip_id=chip_id,
        source_updated_at=updated_at,
        status="invalid" if invalid else "resolved" if static.resolved else "unresolved",
        reason=static.reason,
        runs=runs,
        issues=top_issues,
        has_manual_rounds=has_manual,
        target_override_allowed=not has_manual,
        target_override_reason=MANUAL_TARGET_OVERRIDE_REASON if has_manual else None,
    )
