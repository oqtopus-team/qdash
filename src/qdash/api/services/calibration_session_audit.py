"""The audit of a calibration session: the same history an agent session keeps, for its work.

A calibration session groups the pipeline runs and agent sessions started for one objective.
Its audit uses the agent session audit's mechanisms (``audit_timeline``) and event schema
(``AgentAuditEvent``): a read-time projection of authoritative records, snapshots bound to a
fingerprint, cursors, an export, and one kind of written record, an append-only decision with
a frozen snapshot of its evidence. History and execution control stay separate: recording a
decision grants nothing, and a pipeline run keeps the approval of its exact request, the
execution lock, and the session's admission rules; an agent session keeps its policy and gates.

The events, each from a record that already exists:

- ``session_created`` and ``session_closed``: the calibration session record.
- ``decision``: a ``CalibrationDecisionDocument``. Its interpretation and recommendation are
  the recorder's statements; a decision without a reported model is ``client_reported``.
- ``pipeline_requested``: a ``CalibrationPipelineRunDocument``, with the exact normalized spec
  QDash validated, the decision it carries out (named by the request, never inferred), and
  the launch origin the client reported.
- ``pipeline_dispatch``: the run's dispatch state, including refused and unknown outcomes.
- ``measurement``: each step execution of the run's flow run, with the target task results'
  executed run parameters and outputs.
- ``agent_session_linked``: each agent session created in the session; the events of an
  admitted one follow with ``agent_session_id`` set, exactly as its own audit shows them.

What QDash never receives is never shown as if it were recorded: a host's approval card or
dialog, and a declined approval, are outside QDash. An event lists such facts in ``missing``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from bunnet import SortDirection
from fastapi import HTTPException, status

from qdash.api.schemas.agent_session import AgentAuditEvent
from qdash.api.schemas.calibration_session import (
    CalibrationAuditSessionHeader,
    CalibrationConclusionModel,
    CalibrationDecisionResponse,
    CalibrationExperimentMeasurement,
    CalibrationExperimentPlanModel,
    CalibrationExperimentRow,
    CalibrationLatestRequestedRun,
    CalibrationMeasuredTask,
    CalibrationMeasuredValue,
    CalibrationParameterCheck,
    CalibrationSessionAuditResponse,
    ListCalibrationDecisionsResponse,
    RecordCalibrationDecisionRequest,
    RequestedParameterChangeModel,
)
from qdash.api.services.agent_execution_links import OPEN_EXECUTION_STATUSES
from qdash.api.services.agent_session_audit import (
    KIND_RANK as AGENT_KIND_RANK,
)
from qdash.api.services.agent_session_audit import (
    AgentSessionAuditService,
)
from qdash.api.services.agent_session_gate import load_agent_session
from qdash.api.services.audit_timeline import (
    DEFAULT_PAGE_SIZE,
    AuditSnapshot,
    DecisionLedger,
    bounded_text,
    decision_request_hash,
    fingerprint,
    json_safe,
    number_events,
    read_export,
    read_page,
    scalar,
    scalar_parameters,
    utc,
)
from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import (
    CalibrationAdmission,
    CalibrationDecisionOutcome,
    CalibrationExperimentStage,
    CalibrationPipelineRunStatus,
    CalibrationSessionStatus,
)
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationConclusion,
    CalibrationDecisionDocument,
    CalibrationExperimentPlan,
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qdash.api.schemas.calibration_pipeline import ResolvedPipelineTargets

# Decisions one calibration session may record, as for an agent session.
MAX_DECISIONS_PER_SESSION = 2000
MAX_DETAIL_DECISIONS = 200
MAX_TASKS_PER_EVENT = 100
MAX_SNAPSHOT_TASKS = 50
OPEN_TASK_STATUSES = frozenset({"running", "scheduled", "pending"})
STOPPED_STATUSES = frozenset({"failed", "cancelled"})
# Output parameters the candidate comparison shows, by response field.
MEASURED_PARAMETERS = {
    "gate_time_ns": "zx90_gate_time",
    "cr_duration_ns": "cr_duration",
    "cr_amplitude": "cr_amplitude",
    "gate_fidelity": "zx90_gate_fidelity",
}
# Cause before effect for events that share a time; agent session kinds keep their order.
KIND_RANK = {
    "session_created": 0,
    "decision": 1,
    "pipeline_requested": 2,
    "pipeline_dispatch": 3,
    "agent_session_linked": 4,
    **{kind: 5 + rank for kind, rank in AGENT_KIND_RANK.items() if kind != "decision"},
    "measurement": 6,
    "session_closed": 99,
}
_TASK_FIELDS = {
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
_EPOCH = datetime.min.replace(tzinfo=UTC)

CALIBRATION_AUDIT_NOTES = [
    "Every event comes from a QDash record; nothing is inferred to fill a gap, and no causal "
    "link is drawn from timestamps. A fact the records do not hold is listed in the event's "
    "`missing`.",
    "A pipeline run carries out a decision only when the request that started it named the "
    "decision (`decision_id`). Execution outcomes are the server's records; decision text is "
    "the recorder's statement (`agent_reported` when the client reported a model, otherwise "
    "`client_reported`).",
    "QDash records the request the signed-in user's client sent. A host's approval card or "
    "dialog, and an approval that was declined, never reach QDash: an approved run shows as "
    "its request, a declined one only as a decision no run carries out. `host_approval` in "
    "`missing` says so for a run an agent tool reported.",
    "`model` and the launch origin are what the client reported; QDash does not verify them. "
    "The signed-in user stays responsible for every request.",
    "An admitted agent session's events appear with `agent_session_id`, exactly as its own "
    "audit shows them; that audit keeps its own snapshot and export.",
    "Closing the session records no verdict, and no status says the objective was met. A "
    "recommendation is a decision's conclusion, never inferred.",
    "A response is one snapshot: two consecutive reads of every record agreed. Pages of one "
    "snapshot share its `snapshot_id`; a page is refused when the records changed since the "
    "first page. Records are append-only through the QDash API; this is an application audit, "
    "not a tamper-proof ledger.",
]


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
                    "run": {key: _param_value(value) for key, value in sorted(run.items())},
                }
            )
    return calls


PAIR_STEP_TYPES = frozenset({"TwoQubitCalibration", "CustomTwoQubit", "GenerateCRSchedule"})


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


# ---------------------------------------------------------------------- records


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _param_value(entry: Any) -> Any:
    if isinstance(entry, dict):
        return scalar(entry.get("value"))
    return scalar(entry)


class _Records:
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
            docs.sort(key=lambda doc: (utc(doc.get("start_at")) or _EPOCH, doc["execution_id"]))
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
                _TASK_FIELDS,
                sort=[("start_at", 1), ("task_id", 1)],
            ):
                self.tasks[str(task["task_id"])] = task
                self.tasks_by_execution[str(task.get("execution_id"))].append(task)

    def executions_of(self, run: CalibrationPipelineRunDocument) -> list[dict[str, Any]]:
        return list(self.flows.get(run.flow_run_id, [])) if run.flow_run_id else []

    def run_tasks(self, run: CalibrationPipelineRunDocument) -> list[dict[str, Any]]:
        return [
            task
            for execution in self.executions_of(run)
            for task in self.tasks_by_execution.get(str(execution["execution_id"]), [])
        ]


def _task_facts(task: dict[str, Any]) -> dict[str, Any]:
    outputs, dropped_outputs = scalar_parameters(task.get("output_parameters"))
    executed, dropped_run = scalar_parameters(task.get("run_parameters"))
    facts: dict[str, Any] = {
        "task_id": str(task["task_id"]),
        "name": task.get("name"),
        "qid": task.get("qid"),
        "status": task.get("status"),
        "execution_id": task.get("execution_id"),
        "elapsed_seconds": _number(task.get("elapsed_time")),
        "executed_run_parameters": executed,
        "outputs": outputs,
    }
    if dropped_outputs or dropped_run:
        facts["omitted_non_scalar_or_extra_parameters"] = dropped_outputs + dropped_run
    return facts


def _measured_value(task: dict[str, Any], parameter: str) -> CalibrationMeasuredValue | None:
    output = (task.get("output_parameters") or {}).get(parameter)
    if not isinstance(output, dict):
        return None
    value = _number(output.get("value"))
    if value is None:
        return None
    error = _number(output.get("error"))
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
    ordered = sorted(tasks, key=lambda task: (utc(task.get("start_at")) or _EPOCH, task["task_id"]))
    completed = [task for task in ordered if task.get("status") == "completed"]
    by_end = sorted(completed, key=lambda task: utc(task.get("end_at")) or _EPOCH)
    measured: dict[str, CalibrationMeasuredValue | None] = {}
    for field_name, parameter in MEASURED_PARAMETERS.items():
        value = None
        for task in reversed(by_end):
            value = _measured_value(task, parameter)
            if value is not None:
                break
        measured[field_name] = value
    durations = [_number(task.get("elapsed_time")) for task in ordered]
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
                elapsed_seconds=_number(task.get("elapsed_time")),
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
            executed = _param_value(found[-1]["run_parameters"][change.parameter])
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


def _decision_response(
    doc: CalibrationDecisionDocument,
    carried_out_by: Iterable[str] = (),
    superseded_by: str | None = None,
) -> CalibrationDecisionResponse:
    data = doc.model_dump(exclude={"id", "request_hash", "quota_slot", "revision_id"})
    return CalibrationDecisionResponse.model_validate(
        {
            **data,
            "carried_out_by_run_ids": list(carried_out_by),
            "superseded_by_decision_id": superseded_by,
        }
    )


@dataclass
class SearchView:
    """The search a calibration session's audit records, as the detail read shows it."""

    experiments: list[CalibrationExperimentRow]
    decisions: list[CalibrationDecisionResponse]
    decision_total: int
    recommendation: CalibrationDecisionResponse | None
    latest_requested_run: CalibrationLatestRequestedRun | None


def _load_session(project_id: str, calibration_session_id: str) -> CalibrationSessionDocument:
    doc = CalibrationSessionDocument.find_one(
        {"project_id": project_id, "calibration_session_id": calibration_session_id}
    ).run()
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calibration session '{calibration_session_id}' not found",
        )
    return doc


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


_LEDGER: DecisionLedger[CalibrationDecisionDocument] = DecisionLedger(
    CalibrationDecisionDocument, limit=MAX_DECISIONS_PER_SESSION, noun="calibration session"
)


class CalibrationSessionAuditService:
    """Record decisions in a calibration session and read its audit."""

    # ------------------------------------------------------------------ decisions

    def record_decision(
        self,
        *,
        project_id: str,
        calibration_session_id: str,
        username: str,
        body: RecordCalibrationDecisionRequest,
    ) -> CalibrationDecisionResponse:
        """Append one decision to a calibration session the signed-in user created.

        Like an agent session decision, recording changes no state and passes no execution
        gate, so it is allowed in every status, including a closed session. A retry with the
        same idempotency key and request returns the same record.
        """
        session = _load_session(project_id, calibration_session_id)
        if username != session.created_by:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Only {session.created_by}, who created this calibration session, records "
                    "its decisions"
                ),
            )
        request_hash = decision_request_hash(body)
        scope = {"project_id": project_id, "calibration_session_id": calibration_session_id}
        existing = _LEDGER.precheck(scope, body.idempotency_key, request_hash)
        if existing is not None:
            return _decision_response(existing)

        records = _Records(session)
        runs = {run.run_id: run for run in records.runs}
        decisions = {d.decision_id: d for d in records.decisions}
        run_ids = list(dict.fromkeys(body.evidence_run_ids))
        unknown_runs = [run_id for run_id in run_ids if run_id not in runs]
        if unknown_runs:
            raise _conflict(f"Not pipeline runs of this session: {', '.join(unknown_runs)}")
        decision_ids = list(dict.fromkeys(body.evidence_decision_ids))
        referenced = decision_ids + (
            [body.supersedes_decision_id] if body.supersedes_decision_id else []
        )
        unknown_decisions = [d for d in referenced if d not in decisions]
        if unknown_decisions:
            raise _conflict(f"Not decisions of this session: {', '.join(unknown_decisions)}")
        task_ids = list(dict.fromkeys(body.evidence_task_ids))
        tasks = self._check_tasks(session, task_ids, body.experiment)
        if body.conclusion is not None:
            self._check_conclusion(body.conclusion, run_ids, decision_ids, runs, decisions)

        fields: dict[str, Any] = {
            "project_id": project_id,
            "calibration_session_id": calibration_session_id,
            "chip_id": session.chip_id,
            "idempotency_key": body.idempotency_key,
            "request_hash": request_hash,
            "recorded_by": username,
            "session_status_at_record": session.status.value,
            "assessment": body.assessment,
            "interpretation": body.interpretation,
            "next_action": body.next_action,
            "next_detail": body.next_detail,
            "evidence_run_ids": run_ids,
            "evidence_task_ids": task_ids,
            "evidence_decision_ids": decision_ids,
            "supersedes_decision_id": body.supersedes_decision_id,
            "experiment": (
                CalibrationExperimentPlan.model_validate(body.experiment.model_dump())
                if body.experiment
                else None
            ),
            "conclusion": (
                CalibrationConclusion.model_validate(body.conclusion.model_dump())
                if body.conclusion
                else None
            ),
            "model": body.model,
            "evidence_snapshot": json_safe(
                self._snapshot(records, run_ids, tasks, decision_ids, body.experiment)
            ),
        }
        return _decision_response(_LEDGER.insert(scope, fields, request_hash))

    @staticmethod
    def _check_tasks(
        session: CalibrationSessionDocument,
        task_ids: list[str],
        experiment: CalibrationExperimentPlanModel | None,
    ) -> list[dict[str, Any]]:
        if not task_ids:
            return []
        found = {
            str(doc["task_id"]): doc
            for doc in TaskResultHistoryDocument.get_motor_collection().find(
                {"project_id": session.project_id, "task_id": {"$in": task_ids}}, _TASK_FIELDS
            )
        }
        foreign = [
            task_id
            for task_id in task_ids
            if task_id not in found or found[task_id].get("chip_id") != session.chip_id
        ]
        if foreign:
            raise _conflict(
                f"Not task results on chip {session.chip_id} in this project: {', '.join(foreign)}"
            )
        if experiment is not None:
            elsewhere = [t for t in task_ids if found[t].get("qid") != experiment.target]
            if elsewhere:
                raise _conflict(
                    f"Task results not on target {experiment.target}: {', '.join(elsewhere)}"
                )
        return [found[task_id] for task_id in task_ids]

    @staticmethod
    def _check_conclusion(
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
            if d.experiment is not None
            and d.experiment.stage == CalibrationExperimentStage.BASELINE
        }
        of_candidate = [
            (plan, ran) for plan, ran in plans if plan.candidate_id == candidate and ran
        ]
        if conclusion.outcome == CalibrationDecisionOutcome.KEEP_BASELINE:
            if candidate not in baselines:
                raise _unprocessable(
                    f"keep_baseline names {candidate}, which no decision of this session "
                    "proposed as a baseline"
                )
            if not of_candidate:
                raise _unprocessable(f"keep_baseline cites no measured evidence of {candidate}")
            return
        if candidate in baselines:
            raise _unprocessable(
                f"Candidate {candidate} is the baseline; conclude keep_baseline to keep it"
            )
        if not any(
            plan.stage == CalibrationExperimentStage.CONFIRMATION for plan, _ in of_candidate
        ):
            raise _unprocessable(
                f"recommend_candidate cites no confirmation run of {candidate}; screening alone "
                "does not back a recommendation"
            )

    @staticmethod
    def _snapshot(
        records: _Records,
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
            run_tasks = [
                t for t in records.run_tasks(run) if target is None or t.get("qid") == target
            ]
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
                    "tasks": [_task_facts(t) for t in run_tasks[:MAX_SNAPSHOT_TASKS]],
                    "omitted_tasks": max(0, len(run_tasks) - MAX_SNAPSHOT_TASKS),
                    "missing": missing,
                }
            )
        return {
            "pipeline_runs": snapshot_runs,
            "tasks": [_task_facts(task) for task in tasks],
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

    def list_decisions(
        self, *, project_id: str, calibration_session_id: str
    ) -> ListCalibrationDecisionsResponse:
        """A calibration session's decisions, oldest first."""
        session = _load_session(project_id, calibration_session_id)
        records = _Records(session)
        items = self._decision_responses(records)
        return ListCalibrationDecisionsResponse(items=items, total=len(items))

    @staticmethod
    def _decision_responses(records: _Records) -> list[CalibrationDecisionResponse]:
        carried: dict[str, list[str]] = defaultdict(list)
        for run in records.runs:
            if run.decision_id:
                carried[run.decision_id].append(run.run_id)
        superseded = {
            d.supersedes_decision_id: d.decision_id
            for d in records.decisions
            if d.supersedes_decision_id
        }
        return [
            _decision_response(d, carried.get(d.decision_id, []), superseded.get(d.decision_id))
            for d in records.decisions
        ]

    # ------------------------------------------------------------------ search view

    def search(self, session: CalibrationSessionDocument) -> SearchView:
        """Experiments, decisions, the recommendation, and the latest requested run."""
        records = _Records(session)
        decisions = self._decision_responses(records)
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
            latest_requested_run=self._latest_requested_run(records, docs, recommendation),
        )

    @staticmethod
    def _latest_requested_run(
        records: _Records,
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
                candidate == recommended
                if candidate is not None and recommended is not None
                else None
            ),
        )

    # ------------------------------------------------------------------ timeline

    def timeline(self, session: CalibrationSessionDocument) -> list[AgentAuditEvent]:
        """Every event of the calibration session, in stable chronological order."""
        records = _Records(session)
        events: list[AgentAuditEvent] = []
        cited_runs = {run_id for d in records.decisions for run_id in d.evidence_run_ids}
        superseded = {
            d.supersedes_decision_id: d.decision_id
            for d in records.decisions
            if d.supersedes_decision_id
        }

        def add(**fields: Any) -> None:
            fields["at"] = utc(fields["at"])
            fields.setdefault("state_version", 0)
            events.append(AgentAuditEvent(sequence=0, **fields))

        add(
            event_id=f"session_created:{session.calibration_session_id}",
            at=session.created_at,
            kind="session_created",
            summary=f"{session.created_by} opened '{bounded_text(session.objective, 200)}' on "
            f"{session.chip_id}",
            actor=session.created_by,
            actor_kind="human",
            provenance="server_record",
            data={"objective": session.objective, "chip_id": session.chip_id},
        )

        for decision in records.decisions:
            plan = decision.experiment
            conclusion = decision.conclusion
            summary = f"Next {decision.next_action.value}"
            if plan is not None:
                summary = f"Proposed {plan.stage.value} of {plan.candidate_id} on {plan.target}" + (
                    ": "
                    + ", ".join(
                        f"{c.task_name}.{c.parameter}={c.value}" for c in plan.requested_changes
                    )
                    if plan.requested_changes
                    else ""
                )
            if conclusion is not None:
                summary = f"Concluded {conclusion.outcome.value}" + (
                    f" ({conclusion.recommended_candidate_id})"
                    if conclusion.recommended_candidate_id
                    else ""
                )
            reported = decision.model is not None
            add(
                event_id=f"decision:{decision.decision_id}",
                at=decision.recorded_at,
                kind="decision",
                summary=summary,
                actor=decision.recorded_by,
                actor_kind="agent" if reported else "unknown",
                provenance="agent_reported" if reported else "client_reported",
                status="superseded" if decision.decision_id in superseded else "recorded",
                decision_id=decision.decision_id,
                model=decision.model,
                missing=([] if decision.assessment else ["assessment"])
                + ([] if reported else ["model"]),
                data={
                    "assessment": decision.assessment.value if decision.assessment else None,
                    "interpretation": decision.interpretation,
                    "next_action": decision.next_action.value,
                    "next_detail": decision.next_detail,
                    "experiment": plan.model_dump(mode="json") if plan else None,
                    "conclusion": conclusion.model_dump(mode="json") if conclusion else None,
                    "evidence_run_ids": decision.evidence_run_ids,
                    "evidence_task_ids": decision.evidence_task_ids,
                    "evidence_decision_ids": decision.evidence_decision_ids,
                    "supersedes_decision_id": decision.supersedes_decision_id,
                    "superseded_by_decision_id": superseded.get(decision.decision_id),
                    "session_status_at_record": decision.session_status_at_record,
                    "evidence_snapshot": decision.evidence_snapshot,
                    "agent_reported_fields": [
                        "interpretation",
                        "next_detail",
                        "experiment",
                        "conclusion",
                    ],
                },
            )

        for run in records.runs:
            self._run_events(records, run, run.run_id in cited_runs, add)

        for agent in records.agents:
            admission = agent.calibration_admission
            add(
                event_id=f"agent_session_linked:{agent.session_id}",
                at=agent.created_at,
                kind="agent_session_linked",
                summary=(
                    f"Agent session {agent.session_id} created in the session "
                    f"({admission.value if admission else 'no admission'})"
                ),
                actor=agent.created_by,
                actor_kind="human",
                provenance="server_record",
                status=admission.value if admission else None,
                status_is_current=True,
                agent_session_id=agent.session_id,
                data={
                    "admission": admission.value if admission else None,
                    "autonomy": agent.policy.autonomy.value,
                    "qids": list(agent.policy.qids),
                    "audit_path": f"/agent-sessions/{agent.session_id}/audit",
                    "note": (
                        "Only an admitted agent session operated; its events follow. A pending "
                        "or rejected one never operated."
                    ),
                },
            )
            if admission != CalibrationAdmission.ADMITTED:
                continue
            loaded = load_agent_session(session.project_id, agent.session_id)
            for event in AgentSessionAuditService().timeline(loaded):
                events.append(
                    event.model_copy(
                        update={
                            "event_id": f"agent_session:{agent.session_id}:{event.event_id}",
                            "agent_session_id": agent.session_id,
                        }
                    )
                )

        if session.status == CalibrationSessionStatus.CLOSED and session.closed_at is not None:
            add(
                event_id=f"session_closed:{session.calibration_session_id}",
                at=session.closed_at,
                kind="session_closed",
                summary=f"{session.closed_by or 'Someone'} closed the session",
                actor=session.closed_by,
                actor_kind="human",
                provenance="server_record",
                status=CalibrationSessionStatus.CLOSED.value,
                missing=[] if session.closed_by else ["actor"],
                data={
                    "closing_note": session.closing_note,
                    "closed_with_unknown_runs": list(session.closed_with_unknown_runs),
                    "closed_with_unknown_starts": [
                        r.model_dump(mode="json") for r in session.closed_with_unknown_starts
                    ],
                    "note": "Closing records no verdict on the objective and cancels nothing.",
                },
            )

        number_events(events, KIND_RANK)
        return events

    @staticmethod
    def _run_events(
        records: _Records, run: CalibrationPipelineRunDocument, cited: bool, add: Any
    ) -> None:
        origin = run.reported_origin
        agent_tool = origin is not None and origin.source == "agent_tool"
        missing: list[str] = []
        if run.spec is None:
            missing.append("requested_spec")
        if agent_tool:
            missing.append("host_approval")
            if run.decision_id is None:
                missing.append("decision")
        add(
            event_id=f"pipeline_requested:{run.run_id}",
            at=run.requested_at,
            kind="pipeline_requested",
            summary=(
                f"{run.requested_by} requested pipeline '{run.pipeline_name or run.run_id}'"
                + (f" for decision {run.decision_id}" if run.decision_id else "")
                + (f" (reported: {origin.tool})" if origin else "")
            ),
            actor=run.requested_by,
            actor_kind="agent" if agent_tool else "unknown",
            provenance="server_record",
            pipeline_run_id=run.run_id,
            decision_id=run.decision_id,
            missing=missing,
            data={
                "idempotency_key": run.idempotency_key,
                "pipeline_name": run.pipeline_name,
                "backend_name": run.backend_name,
                "attempts": run.attempts,
                "requested_task_calls": requested_task_calls(run.spec),
                "reported_origin": origin.model_dump(mode="json") if origin else None,
                "actor_kind_basis": "client_reported_origin" if agent_tool else None,
                "approval": (
                    "Not recorded by QDash: the request reached QDash under the signed-in user's "
                    "token; a host's approval is outside QDash."
                ),
            },
        )
        dispatch = run_dispatch_status(run)
        executions = records.executions_of(run)
        dispatch_missing: list[str] = []
        if dispatch == CalibrationPipelineRunStatus.DISPATCHED and not executions:
            dispatch_missing.append("execution")
        terminal = bool(executions) and all(
            str(e.get("status")) not in OPEN_EXECUTION_STATUSES for e in executions
        )
        if terminal and not cited:
            dispatch_missing.append("decision")
        notes = {
            CalibrationPipelineRunStatus.REJECTED: "Refused before any flow run existed; nothing ran.",
            CalibrationPipelineRunStatus.UNKNOWN: (
                "The launch may have created a flow run; QDash does not reconcile it with Prefect."
            ),
            CalibrationPipelineRunStatus.DISPATCHING: "The launch has not reported back.",
        }
        add(
            event_id=f"pipeline_dispatch:{run.run_id}",
            at=run.updated_at,
            kind="pipeline_dispatch",
            summary=f"Dispatch of {run.pipeline_name or run.run_id}: {dispatch.value}",
            actor=None,
            actor_kind="server",
            provenance="server_record",
            status=dispatch.value,
            status_is_current=True,
            pipeline_run_id=run.run_id,
            decision_id=run.decision_id,
            execution_id=run.execution_id,
            missing=dispatch_missing,
            data={
                "flow_run_id": run.flow_run_id,
                "attempts": run.attempts,
                "error_recorded": bool(run.error),
                "note": notes.get(dispatch),
            },
        )
        for execution in executions:
            tasks = records.tasks_by_execution.get(str(execution["execution_id"]), [])
            execution_status = str(execution.get("status") or "")
            event_missing = (
                ["task_result"] if execution_status in {"completed", "failed"} and not tasks else []
            )
            add(
                event_id=f"measurement:{execution['execution_id']}",
                at=execution.get("start_at") or run.updated_at,
                kind="measurement",
                summary=(
                    f"Execution {execution['execution_id']}: {execution_status}; "
                    f"{len(tasks)} task result{'s' if len(tasks) != 1 else ''}"
                ),
                actor=run.requested_by,
                actor_kind="worker",
                provenance="server_record",
                status=execution_status,
                status_is_current=True,
                pipeline_run_id=run.run_id,
                decision_id=run.decision_id,
                execution_id=str(execution["execution_id"]),
                missing=event_missing,
                data={
                    "step_index": (execution.get("note") or {}).get("step_index"),
                    "started_at": utc(execution.get("start_at")),
                    "finished_at": utc(execution.get("end_at")),
                    "tasks": [_task_facts(t) for t in tasks[:MAX_TASKS_PER_EVENT]],
                    "omitted_tasks": max(0, len(tasks) - MAX_TASKS_PER_EVENT),
                },
            )

    # ------------------------------------------------------------------ reads

    @staticmethod
    def _header(session: CalibrationSessionDocument) -> CalibrationAuditSessionHeader:
        scope = {
            "project_id": session.project_id,
            "calibration_session_id": session.calibration_session_id,
        }
        return CalibrationAuditSessionHeader(
            calibration_session_id=session.calibration_session_id,
            project_id=session.project_id,
            chip_id=session.chip_id,
            objective=session.objective,
            created_by=session.created_by,
            created_at=cast("datetime", utc(session.created_at)),
            status=session.status,
            pipeline_run_total=CalibrationPipelineRunDocument.find(scope).count(),
            agent_session_total=AgentSessionDocument.find(scope).count(),
            decision_total=CalibrationDecisionDocument.find(scope).count(),
        )

    def _read_once(
        self, project_id: str, calibration_session_id: str
    ) -> AuditSnapshot[CalibrationAuditSessionHeader]:
        session = _load_session(project_id, calibration_session_id)
        header = self._header(session)
        events = self.timeline(session)
        return AuditSnapshot(header, events, fingerprint(header, events))

    @staticmethod
    def _response(
        snapshot: AuditSnapshot[CalibrationAuditSessionHeader],
        events: list[AgentAuditEvent],
        next_cursor: str | None,
    ) -> CalibrationSessionAuditResponse:
        return CalibrationSessionAuditResponse(
            generated_at=cast("datetime", utc(now())),
            snapshot_id=snapshot.snapshot_id,
            calibration_session=snapshot.header,
            events=events,
            total_events=len(snapshot.events),
            next_cursor=next_cursor,
            complete=next_cursor is None,
            notes=CALIBRATION_AUDIT_NOTES,
        )

    def read_audit(
        self,
        *,
        project_id: str,
        calibration_session_id: str,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> CalibrationSessionAuditResponse:
        """One page of a snapshot of the audit, oldest first, as an agent session's audit pages."""
        page = read_page(
            project_id=project_id,
            scope_id=calibration_session_id,
            noun="calibration session",
            read_once=lambda: self._read_once(project_id, calibration_session_id),
            cursor=cursor,
            limit=limit,
        )
        return self._response(page.snapshot, page.events, page.next_cursor)

    def export_audit(
        self, *, project_id: str, calibration_session_id: str
    ) -> CalibrationSessionAuditResponse:
        """The whole of one snapshot; refused, never cut short, beyond the export bound."""
        snapshot = read_export(
            lambda: self._read_once(project_id, calibration_session_id), "calibration session"
        )
        return self._response(snapshot, snapshot.events, None)
