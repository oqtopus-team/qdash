"""Record loading for a calibration session's audit.

Loads the session and every record its audit reads (pipeline runs, decisions, agent sessions,
the executions of each run's flow run, and their task results) in batched queries, and turns
stored run specs and task results into the plain facts the audit shows. Nothing here
validates, writes, or projects events.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from bunnet import SortDirection
from fastapi import HTTPException, status

from qdash.api.services.audit_timeline import scalar, scalar_parameters, utc
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationDecisionDocument,
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from qdash.datamodel.calibration_session import CalibrationPipelineRunStatus

# Task result fields the audit reads.
TASK_FIELDS = {
    "_id": 0,
    "task_id": 1,
    "name": 1,
    "status": 1,
    "qid": 1,
    "chip_id": 1,
    "execution_id": 1,
    "start_at": 1,
    "end_at": 1,
    "elapsed_time": 1,
    "output_parameters": 1,
    "run_parameters": 1,
}
# Sort key for a record without a time: before every recorded one.
EPOCH = datetime.min.replace(tzinfo=UTC)


def load_session(project_id: str, calibration_session_id: str) -> CalibrationSessionDocument:
    """The calibration session of the project, or 404."""
    doc = CalibrationSessionDocument.find_one(
        {"project_id": project_id, "calibration_session_id": calibration_session_id}
    ).run()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calibration session '{calibration_session_id}' not found",
        )
    return doc


def run_dispatch_status(run: CalibrationPipelineRunDocument) -> CalibrationPipelineRunStatus:
    """The run's dispatch status with staleness applied, as every other read reports it."""
    from qdash.api.services.calibration_session_service import dispatch_status

    return dispatch_status(run)


def run_target_qids(run: CalibrationPipelineRunDocument | dict[str, Any]) -> list[str]:
    """The qubits QDash resolved for a dispatched run, from its stored dispatch response."""
    response = run.get("response") if isinstance(run, dict) else run.response
    targets = (response or {}).get("targets") or {}
    qids = targets.get("qids") if isinstance(targets, dict) else None
    return [str(qid) for qid in qids] if isinstance(qids, list) else []


def number(value: Any) -> float | None:
    """A numeric value as a float; None for a boolean or a non-number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def param_value(entry: Any) -> Any:
    """A stored parameter's scalar value, from a ``{"value": ...}`` entry or a bare value."""
    if isinstance(entry, dict):
        return scalar(entry.get("value"))
    return scalar(entry)


def requested_task_calls(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Each task call of a stored spec with the run parameters it requested, as scalars."""
    calls: list[dict[str, Any]] = []
    for index, step in enumerate((spec or {}).get("steps") or []):
        if not isinstance(step, dict):
            continue
        for task in step.get("tasks") or []:
            if isinstance(task, str):
                task = {"name": task}  # noqa: PLW2901 - a task named without settings
            if not isinstance(task, dict):
                continue
            raw_run = task.get("run")
            run: dict[str, Any] = raw_run if isinstance(raw_run, dict) else {}
            calls.append(
                {
                    "step": step.get("step_name") or step.get("name") or f"steps[{index}]",
                    "task_name": str(task.get("name") or ""),
                    "call_id": task.get("call_id"),
                    "run": {key: param_value(value) for key, value in sorted(run.items())},
                }
            )
    return calls


def task_facts(task: dict[str, Any]) -> dict[str, Any]:
    """A task result's identity, status, executed run parameters, and outputs, as scalars."""
    outputs, dropped_outputs = scalar_parameters(task.get("output_parameters"))
    executed, dropped_run = scalar_parameters(task.get("run_parameters"))
    facts: dict[str, Any] = {
        "task_id": str(task["task_id"]),
        "name": task.get("name"),
        "qid": task.get("qid"),
        "status": task.get("status"),
        "execution_id": task.get("execution_id"),
        "elapsed_seconds": number(task.get("elapsed_time")),
        "executed_run_parameters": executed,
        "outputs": outputs,
    }
    if dropped_outputs or dropped_run:
        facts["omitted_non_scalar_or_extra_parameters"] = dropped_outputs + dropped_run
    return facts


class CalibrationAuditRecords:
    """Every record of one calibration session its audit reads, in batched queries."""

    def __init__(self, session: CalibrationSessionDocument) -> None:
        project_id, chip_id = session.project_id, session.chip_id
        scope = {"project_id": project_id, "calibration_session_id": session.calibration_session_id}
        self.session = session
        self.runs = cast(
            "list[CalibrationPipelineRunDocument]",
            CalibrationPipelineRunDocument.find(
                scope,
                sort=[
                    ("requested_at", SortDirection.ASCENDING),
                    ("run_id", SortDirection.ASCENDING),
                ],
            ).run(),
        )
        self.decisions = cast(
            "list[CalibrationDecisionDocument]",
            CalibrationDecisionDocument.find(
                scope,
                sort=[
                    ("recorded_at", SortDirection.ASCENDING),
                    ("quota_slot", SortDirection.ASCENDING),
                ],
            ).run(),
        )
        self.agents = cast(
            "list[AgentSessionDocument]",
            AgentSessionDocument.find(
                scope,
                sort=[
                    ("created_at", SortDirection.ASCENDING),
                    ("session_id", SortDirection.ASCENDING),
                ],
            ).run(),
        )
        flow_run_ids = sorted({run.flow_run_id for run in self.runs if run.flow_run_id})
        self.flows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if flow_run_ids:
            for doc in ExecutionHistoryDocument.get_motor_collection().find(
                {
                    "project_id": project_id,
                    "chip_id": chip_id,
                    "note.flow_run_id": {"$in": flow_run_ids},
                },
                {
                    "_id": 0,
                    "execution_id": 1,
                    "status": 1,
                    "start_at": 1,
                    "end_at": 1,
                    "note.flow_run_id": 1,
                    "note.step_index": 1,
                },
            ):
                self.flows[str(doc["note"]["flow_run_id"])].append(doc)
        for docs in self.flows.values():
            docs.sort(key=lambda doc: (utc(doc.get("start_at")) or EPOCH, doc["execution_id"]))
        execution_ids = sorted(
            {str(e["execution_id"]) for docs in self.flows.values() for e in docs}
        )
        cited = sorted({task_id for d in self.decisions for task_id in d.evidence_task_ids})
        clauses: list[dict[str, Any]] = []
        if execution_ids:
            clauses.append({"execution_id": {"$in": execution_ids}})
        if cited:
            clauses.append({"task_id": {"$in": cited}})
        self.tasks_by_execution: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.tasks: dict[str, dict[str, Any]] = {}
        if clauses:
            for task in TaskResultHistoryDocument.get_motor_collection().find(
                {"project_id": project_id, "chip_id": chip_id, "$or": clauses},
                TASK_FIELDS,
                sort=[("start_at", 1), ("task_id", 1)],
            ):
                self.tasks[str(task["task_id"])] = task
                self.tasks_by_execution[str(task.get("execution_id"))].append(task)

    def executions_of(self, run: CalibrationPipelineRunDocument) -> list[dict[str, Any]]:
        """The executions of the run's flow run, by start time."""
        return list(self.flows.get(run.flow_run_id, [])) if run.flow_run_id else []

    def run_tasks(self, run: CalibrationPipelineRunDocument) -> list[dict[str, Any]]:
        """The task results of the run's executions, execution by execution."""
        return [
            task
            for execution in self.executions_of(run)
            for task in self.tasks_by_execution.get(str(execution["execution_id"]), [])
        ]
