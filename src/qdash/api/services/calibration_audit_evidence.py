"""Evidence validation for calibration session decisions and the runs that carry them out.

Checks a pipeline request's ``decision_id`` against the decision and the validated spec, checks
the task results and conclusion a decision cites, and builds the frozen snapshot of the cited
evidence a decision stores. Validation reads records and raises HTTP errors; it writes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from qdash.api.services.audit_timeline import utc
from qdash.api.services.calibration_audit_records import (
    TASK_FIELDS,
    CalibrationAuditRecords,
    run_dispatch_status,
    task_facts,
)
from qdash.datamodel.calibration_session import (
    CalibrationDecisionOutcome,
    CalibrationExperimentStage,
    CalibrationPipelineRunStatus,
)
from qdash.dbmodel.calibration_session import (
    CalibrationDecisionDocument,
    CalibrationExperimentPlan,
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.api.schemas.calibration_pipeline import ResolvedPipelineTargets
    from qdash.api.schemas.calibration_session import (
        CalibrationConclusionModel,
        CalibrationExperimentPlanModel,
    )

# Task facts a decision's snapshot keeps per cited run.
MAX_SNAPSHOT_TASKS = 50
PAIR_STEP_TYPES = frozenset({"TwoQubitCalibration", "CustomTwoQubit", "GenerateCRSchedule"})


def conflict(detail: str) -> HTTPException:
    """A 409 for evidence that is not this session's."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def unprocessable(detail: str) -> HTTPException:
    """A 422 for evidence that does not back the statement."""
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def _pair_target_problem(target: str, spec: dict[str, Any] | None) -> str | None:
    """Why a directed coupling target does not match the validated spec, or None.

    A coupling target (``control-target``) needs a two-qubit step. When every two-qubit step
    lists its pairs (``execution_mode`` manual), the directed pair must be one of them, so a
    decision about ``1-0`` never links to a run that measures ``0-1``. A step that selects its
    pairs at run time cannot be checked here, so only the qubits are compared.
    """
    if spec is None:
        return None
    control, _, measured = target.partition("-")
    steps = [step for step in spec.get("steps") or [] if isinstance(step, dict)]
    pair_steps = [step for step in steps if step.get("type") in PAIR_STEP_TYPES]
    if not pair_steps:
        return f"proposes coupling {target}, but the spec has no two-qubit step"
    if any(not step.get("rounds") for step in pair_steps):
        return None
    listed = [
        f"{pair[0]}-{pair[1]}"
        for step in pair_steps
        for round_ in step["rounds"]
        for pair in round_
        if isinstance(pair, (list, tuple)) and len(pair) == 2
    ]
    if f"{control}-{measured}" in listed:
        return None
    return (
        f"proposes directed coupling {target}, which no manual round of the spec measures "
        f"(it measures {', '.join(dict.fromkeys(listed)) or 'no pair'})"
    )


def check_run_decision(
    session: CalibrationSessionDocument,
    decision_id: str,
    targets: ResolvedPipelineTargets | None,
    spec: dict[str, Any] | None = None,
) -> CalibrationDecisionDocument:
    """The decision a pipeline request names, checked before anything is recorded.

    It must be a decision of the same session that proposed an experiment, and the
    experiment's target must be among the qubits the validated spec targets. A directed
    coupling target must also match the spec's two-qubit steps (see ``_pair_target_problem``).
    """
    decision = CalibrationDecisionDocument.find_one(
        {
            "project_id": session.project_id,
            "calibration_session_id": session.calibration_session_id,
            "decision_id": decision_id,
        }
    ).run()
    if decision is None or decision.experiment is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"decision_id {decision_id} names no decision with an experiment in calibration "
                f"session {session.calibration_session_id}; record the decision first"
            ),
        )
    qids = list(getattr(targets, "qids", None) or [])
    target = decision.experiment.target
    if qids and not set(target.split("-")) <= set(qids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Decision {decision_id} proposes target {target}, outside the spec's targets "
                f"({', '.join(qids)})"
            ),
        )
    if "-" in target:
        problem = _pair_target_problem(target, spec)
        if problem is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Decision {decision_id} {problem}",
            )
    return decision


def check_evidence_tasks(
    session: CalibrationSessionDocument,
    task_ids: list[str],
    experiment: CalibrationExperimentPlanModel | None,
) -> list[dict[str, Any]]:
    """The cited task results, in citation order; each must be on the session's chip.

    With an experiment, each must also be on the experiment's target.
    """
    if not task_ids:
        return []
    found = {
        str(doc["task_id"]): doc
        for doc in TaskResultHistoryDocument.get_motor_collection().find(
            {"project_id": session.project_id, "task_id": {"$in": task_ids}}, TASK_FIELDS
        )
    }
    foreign = [
        task_id
        for task_id in task_ids
        if task_id not in found or found[task_id].get("chip_id") != session.chip_id
    ]
    if foreign:
        raise conflict(
            f"Not task results on chip {session.chip_id} in this project: {', '.join(foreign)}"
        )
    if experiment is not None:
        elsewhere = [t for t in task_ids if found[t].get("qid") != experiment.target]
        if elsewhere:
            raise conflict(
                f"Task results not on target {experiment.target}: {', '.join(elsewhere)}"
            )
    return [found[task_id] for task_id in task_ids]


def check_conclusion(
    conclusion: CalibrationConclusionModel,
    run_ids: list[str],
    decision_ids: list[str],
    runs: dict[str, CalibrationPipelineRunDocument],
    decisions: dict[str, CalibrationDecisionDocument],
) -> None:
    """A recommendation rests on cited evidence of its candidate, as the session records it."""
    candidate = conclusion.recommended_candidate_id
    if candidate is None:
        return
    # The plan each cited piece of evidence measured: a run's from the decision it named.
    plans: list[tuple[CalibrationExperimentPlan, bool]] = []
    for run_id in run_ids:
        run = runs[run_id]
        intent = decisions.get(run.decision_id) if run.decision_id else None
        if intent is not None and intent.experiment is not None:
            ran = run_dispatch_status(run) != CalibrationPipelineRunStatus.REJECTED
            plans.append((intent.experiment, ran))
    for decision_id in decision_ids:
        plan = decisions[decision_id].experiment
        if plan is not None:
            plans.append((plan, bool(decisions[decision_id].evidence_task_ids)))
    baselines = {
        d.experiment.candidate_id
        for d in decisions.values()
        if d.experiment is not None and d.experiment.stage == CalibrationExperimentStage.BASELINE
    }
    of_candidate = [(plan, ran) for plan, ran in plans if plan.candidate_id == candidate and ran]
    if conclusion.outcome == CalibrationDecisionOutcome.KEEP_BASELINE:
        if candidate not in baselines:
            raise unprocessable(
                f"keep_baseline names {candidate}, which no decision of this session "
                "proposed as a baseline"
            )
        if not of_candidate:
            raise unprocessable(f"keep_baseline cites no measured evidence of {candidate}")
        return
    if candidate in baselines:
        raise unprocessable(
            f"Candidate {candidate} is the baseline; conclude keep_baseline to keep it"
        )
    if not any(plan.stage == CalibrationExperimentStage.CONFIRMATION for plan, _ in of_candidate):
        raise unprocessable(
            f"recommend_candidate cites no confirmation run of {candidate}; screening alone "
            "does not back a recommendation"
        )


def evidence_snapshot(
    records: CalibrationAuditRecords,
    run_ids: list[str],
    tasks: list[dict[str, Any]],
    decision_ids: list[str],
    experiment: CalibrationExperimentPlanModel | None,
) -> dict[str, Any]:
    """What QDash's records say about the cited evidence now."""
    runs = {run.run_id: run for run in records.runs}
    decisions = {d.decision_id: d for d in records.decisions}
    snapshot_runs: list[dict[str, Any]] = []
    for run_id in run_ids:
        run = runs[run_id]
        intent = decisions.get(run.decision_id) if run.decision_id else None
        target = (
            intent.experiment.target
            if intent is not None and intent.experiment is not None
            else (experiment.target if experiment is not None else None)
        )
        run_tasks = [t for t in records.run_tasks(run) if target is None or t.get("qid") == target]
        missing = [] if target is not None else ["target"]
        snapshot_runs.append(
            {
                "run_id": run_id,
                "dispatch_status": run_dispatch_status(run).value,
                "flow_run_id": run.flow_run_id,
                "decision_id": run.decision_id,
                "target": target,
                "executions": [
                    {
                        "execution_id": e["execution_id"],
                        "status": e.get("status"),
                        "started_at": utc(e.get("start_at")),
                        "finished_at": utc(e.get("end_at")),
                    }
                    for e in records.executions_of(run)
                ],
                "tasks": [task_facts(t) for t in run_tasks[:MAX_SNAPSHOT_TASKS]],
                "omitted_tasks": max(0, len(run_tasks) - MAX_SNAPSHOT_TASKS),
                "missing": missing,
            }
        )
    return {
        "pipeline_runs": snapshot_runs,
        "tasks": [task_facts(task) for task in tasks],
        "decisions": [
            {
                "decision_id": decision_id,
                "next_action": decisions[decision_id].next_action.value,
                "experiment": (
                    plan.model_dump(mode="json")
                    if (plan := decisions[decision_id].experiment) is not None
                    else None
                ),
            }
            for decision_id in decision_ids
        ],
    }
