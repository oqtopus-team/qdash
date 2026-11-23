"""Search projection for a calibration session's detail read.

Projects the session's records into the search it records: one experiment row per proposed
experiment and the run that carried it out, what its task results measured, how its requested
changes compare with the exact request and the executed values, the current recommendation,
and the latest requested run with its recorded outcome (never a hardware state).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from qdash.api.schemas.calibration_session import (
    CalibrationDecisionResponse,
    CalibrationExperimentMeasurement,
    CalibrationExperimentRow,
    CalibrationLatestRequestedRun,
    CalibrationMeasuredTask,
    CalibrationMeasuredValue,
    CalibrationParameterCheck,
    RequestedParameterChangeModel,
)
from qdash.api.services.agent_execution_links import OPEN_EXECUTION_STATUSES
from qdash.api.services.audit_timeline import utc
from qdash.api.services.calibration_audit_decisions import decision_responses
from qdash.api.services.calibration_audit_records import (
    EPOCH,
    CalibrationAuditRecords,
    number,
    param_value,
    requested_task_calls,
    run_dispatch_status,
)
from qdash.datamodel.calibration_session import CalibrationPipelineRunStatus

if TYPE_CHECKING:
    from datetime import datetime

    from qdash.dbmodel.calibration_session import (
        CalibrationDecisionDocument,
        CalibrationExperimentPlan,
        CalibrationPipelineRunDocument,
        CalibrationSessionDocument,
    )

# Most recent decisions the detail read lists.
MAX_DETAIL_DECISIONS = 200
OPEN_TASK_STATUSES = frozenset({"running", "scheduled", "pending"})
STOPPED_STATUSES = frozenset({"failed", "cancelled"})
# Output parameters the candidate comparison shows, by response field.
MEASURED_PARAMETERS = {
    "gate_time_ns": "zx90_gate_time",
    "cr_duration_ns": "cr_duration",
    "cr_amplitude": "cr_amplitude",
    "gate_fidelity": "zx90_gate_fidelity",
}


@dataclass
class SearchView:
    """The search a calibration session's audit records, as the detail read shows it."""

    experiments: list[CalibrationExperimentRow]
    decisions: list[CalibrationDecisionResponse]
    decision_total: int
    recommendation: CalibrationDecisionResponse | None
    latest_requested_run: CalibrationLatestRequestedRun | None


def _measured_value(task: dict[str, Any], parameter: str) -> CalibrationMeasuredValue | None:
    output = (task.get("output_parameters") or {}).get(parameter)
    if not isinstance(output, dict):
        return None
    value = number(output.get("value"))
    if value is None:
        return None
    error = number(output.get("error"))
    return CalibrationMeasuredValue(
        value=value,
        error=error if error else None,
        unit=str(output.get("unit") or ""),
        task_id=str(task["task_id"]),
        task_name=str(task.get("name") or ""),
        execution_id=str(task.get("execution_id") or ""),
    )


def _evidence_status(tasks: list[dict[str, Any]], executions: list[dict[str, Any]]) -> str:
    statuses = [str(task.get("status") or "") for task in tasks]
    if any(str(e.get("status")) in OPEN_EXECUTION_STATUSES for e in executions) or any(
        value in OPEN_TASK_STATUSES for value in statuses
    ):
        return "running"
    if not statuses:
        return "unavailable"
    if all(value == "completed" for value in statuses):
        return "complete"
    if "completed" not in statuses and any(value in STOPPED_STATUSES for value in statuses):
        return "failed"
    return "partial"


def measure(
    run: CalibrationPipelineRunDocument | None,
    executions: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> CalibrationExperimentMeasurement:
    """What the evidence measured, from task results only."""
    ordered = sorted(tasks, key=lambda task: (utc(task.get("start_at")) or EPOCH, task["task_id"]))
    completed = [task for task in ordered if task.get("status") == "completed"]
    by_end = sorted(completed, key=lambda task: utc(task.get("end_at")) or EPOCH)
    measured: dict[str, CalibrationMeasuredValue | None] = {}
    for field_name, parameter in MEASURED_PARAMETERS.items():
        value = None
        for task in reversed(by_end):
            value = _measured_value(task, parameter)
            if value is not None:
                break
        measured[field_name] = value
    durations = [number(task.get("elapsed_time")) for task in ordered]
    ended = [value for value in durations if value is not None]
    starts = [utc(e.get("start_at")) for e in executions]
    ends = [utc(e.get("end_at")) for e in executions]
    execution_seconds = None
    if executions and all(starts) and all(ends):
        first = min(cast("list[datetime]", starts))
        last = max(cast("list[datetime]", ends))
        execution_seconds = (last - first).total_seconds()
    evidence = _evidence_status(ordered, executions)
    if run is not None and run_dispatch_status(run) == CalibrationPipelineRunStatus.REJECTED:
        evidence = "not_run"
    return CalibrationExperimentMeasurement(
        evidence_status=evidence,  # type: ignore[arg-type]
        pipeline_dispatch_status=run_dispatch_status(run) if run is not None else None,
        execution_ids=[str(e["execution_id"]) for e in executions],
        tasks=[
            CalibrationMeasuredTask(
                task_id=str(task["task_id"]),
                name=str(task.get("name") or ""),
                status=str(task.get("status") or ""),
                execution_id=str(task.get("execution_id") or ""),
                start_at=utc(task.get("start_at")),
                end_at=utc(task.get("end_at")),
                elapsed_seconds=number(task.get("elapsed_time")),
            )
            for task in ordered
        ],
        task_seconds=sum(ended) if ended else None,
        execution_seconds=execution_seconds,
        **measured,
    )


def _parameter_checks(
    plan: CalibrationExperimentPlan,
    run: CalibrationPipelineRunDocument | None,
    tasks: list[dict[str, Any]],
) -> list[CalibrationParameterCheck]:
    """Each requested change against the run's exact request and the task's executed value."""
    calls = requested_task_calls(run.spec) if run is not None else []
    checks: list[CalibrationParameterCheck] = []
    for change in plan.requested_changes:
        missing: list[str] = []
        in_spec: Any = None
        if run is None:
            missing.append("pipeline_run")
        elif run.spec is None:
            missing.append("requested_spec")
        else:
            matching = [
                c
                for c in calls
                if c["task_name"] == change.task_name
                and (change.call_id is None or c["call_id"] == change.call_id)
            ]
            if matching and change.parameter in matching[0]["run"]:
                in_spec = matching[0]["run"][change.parameter]
            else:
                missing.append("spec_value")
        executed: Any = None
        found = [
            task
            for task in tasks
            if task.get("name") == change.task_name
            and change.parameter in (task.get("run_parameters") or {})
        ]
        if found:
            executed = param_value(found[-1]["run_parameters"][change.parameter])
        elif run is not None:
            missing.append("executed_value")
        consistent = None
        if in_spec is not None and executed is not None:
            consistent = change.value == in_spec == executed
        elif in_spec is not None:
            consistent = None if change.value == in_spec else False
        checks.append(
            CalibrationParameterCheck(
                task_name=change.task_name,
                call_id=change.call_id,
                parameter=change.parameter,
                requested=change.value,
                in_spec=in_spec,
                executed=executed,
                consistent=consistent,
                missing=missing,
            )
        )
    return checks


def _latest_requested_run(
    records: CalibrationAuditRecords,
    decisions: dict[str, CalibrationDecisionDocument],
    recommendation: CalibrationDecisionResponse | None,
) -> CalibrationLatestRequestedRun | None:
    """The last run by request order with its recorded outcome; never a hardware state.

    Request order does not prove which run wrote last (an earlier request may finish
    later), and a completed execution is not an authoritative write record, so the view
    reports what was requested and how its executions ended, and lists the write as
    missing.
    """
    if not records.runs:
        return None
    run = records.runs[-1]
    dispatch = run_dispatch_status(run)
    executions = records.executions_of(run)
    statuses = [str(e.get("status")) for e in executions]
    outcome: str
    if dispatch == CalibrationPipelineRunStatus.REJECTED:
        outcome = "refused"
    elif dispatch != CalibrationPipelineRunStatus.DISPATCHED:
        outcome = "unknown"
    elif not executions:
        outcome = "no_execution"
    elif any(value in OPEN_EXECUTION_STATUSES for value in statuses):
        outcome = "running"
    elif all(value == "completed" for value in statuses):
        outcome = "completed"
    elif any(value == "completed" for value in statuses):
        outcome = "partial"
    else:
        outcome = "failed"
    intent = decisions.get(run.decision_id) if run.decision_id else None
    candidate = intent.experiment.candidate_id if intent and intent.experiment else None
    ends = [utc(e.get("end_at")) for e in executions]
    recommended = (
        recommendation.conclusion.recommended_candidate_id
        if recommendation is not None and recommendation.conclusion is not None
        else None
    )
    return CalibrationLatestRequestedRun(
        pipeline_run_id=run.run_id,
        requested_at=cast("datetime", utc(run.requested_at)),
        dispatch_status=dispatch,
        execution_outcome=outcome,  # type: ignore[arg-type]
        decision_id=run.decision_id,
        candidate_id=candidate,
        execution_ids=[str(e["execution_id"]) for e in executions],
        finished_at=(
            max(cast("list[datetime]", ends))
            if ends and all(ends) and outcome != "running"
            else None
        ),
        candidate_is_recommended=(
            candidate == recommended if candidate is not None and recommended is not None else None
        ),
    )


def search_view(session: CalibrationSessionDocument) -> SearchView:
    """Experiments, decisions, the recommendation, and the latest requested run."""
    records = CalibrationAuditRecords(session)
    decisions = decision_responses(records)
    recent = decisions[-MAX_DETAIL_DECISIONS:]
    runs_of: dict[str, list[CalibrationPipelineRunDocument]] = defaultdict(list)
    for recorded in records.runs:
        if recorded.decision_id:
            runs_of[recorded.decision_id].append(recorded)
    docs = {d.decision_id: d for d in records.decisions}
    rows: list[CalibrationExperimentRow] = []
    for response in recent:
        doc = docs[response.decision_id]
        plan = doc.experiment
        if plan is None:
            continue
        carried: list[CalibrationPipelineRunDocument | None] = list(
            runs_of.get(doc.decision_id, [])
        )
        for run in carried or [None]:
            if run is not None:
                executions = records.executions_of(run)
                tasks = [t for t in records.run_tasks(run) if t.get("qid") == plan.target]
                measured = measure(run, executions, tasks)
            else:
                tasks = [
                    records.tasks[t]
                    for t in doc.evidence_task_ids
                    if t in records.tasks and records.tasks[t].get("qid") == plan.target
                ]
                measured = (
                    measure(None, [], tasks)
                    if tasks
                    else CalibrationExperimentMeasurement(evidence_status="not_run")
                )
            rows.append(
                CalibrationExperimentRow(
                    sequence=len(rows) + 1,
                    decision_id=doc.decision_id,
                    stage=plan.stage,
                    candidate_id=plan.candidate_id,
                    target=plan.target,
                    requested_changes=[
                        RequestedParameterChangeModel.model_validate(c.model_dump())
                        for c in plan.requested_changes
                    ],
                    rationale=doc.interpretation,
                    model=doc.model,
                    recorded_at=cast("datetime", utc(doc.recorded_at)),
                    pipeline_run_id=run.run_id if run is not None else None,
                    parameter_checks=_parameter_checks(plan, run, tasks),
                    measured=measured,
                )
            )
    recommendation = next(
        (
            d
            for d in reversed(decisions)
            if d.conclusion is not None and d.superseded_by_decision_id is None
        ),
        None,
    )
    return SearchView(
        experiments=rows,
        decisions=recent,
        decision_total=len(decisions),
        recommendation=recommendation,
        latest_requested_run=_latest_requested_run(records, docs, recommendation),
    )
