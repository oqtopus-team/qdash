"""Event projection for a calibration session's audit timeline.

Projects the session's records into ``AgentAuditEvent`` items: the session's creation and
close, each decision, each pipeline run's request, dispatch and measurements, each linked
agent session, and an admitted agent session's own events. Events are numbered in stable
chronological order with cause before effect for events that share a time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdash.api.schemas.agent_session import AgentAuditEvent
from qdash.api.services.agent_execution_links import OPEN_EXECUTION_STATUSES
from qdash.api.services.agent_session_audit import (
    KIND_RANK as AGENT_KIND_RANK,
)
from qdash.api.services.agent_session_audit import (
    AgentSessionAuditService,
)
from qdash.api.services.agent_session_gate import load_agent_session
from qdash.api.services.audit_timeline import bounded_text, number_events, utc
from qdash.api.services.calibration_audit_records import (
    CalibrationAuditRecords,
    requested_task_calls,
    run_dispatch_status,
    task_facts,
)
from qdash.datamodel.calibration_session import (
    CalibrationAdmission,
    CalibrationPipelineRunStatus,
    CalibrationRunKind,
    CalibrationRunTrigger,
    CalibrationSessionOrigin,
    CalibrationSessionStatus,
)

if TYPE_CHECKING:
    from qdash.dbmodel.calibration_session import (
        CalibrationPipelineRunDocument,
        CalibrationSessionDocument,
    )

# Task facts one measurement event lists.
MAX_TASKS_PER_EVENT = 100
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


def session_timeline(session: CalibrationSessionDocument) -> list[AgentAuditEvent]:
    """Every event of the calibration session, in stable chronological order."""
    records = CalibrationAuditRecords(session)
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

    automatic = session.origin == CalibrationSessionOrigin.AUTOMATIC
    add(
        event_id=f"session_created:{session.calibration_session_id}",
        at=session.created_at,
        kind="session_created",
        summary=(
            f"QDash opened an automatic session for {session.created_by}'s run "
            f"'{bounded_text(session.objective, 200)}' on {session.chip_id}"
            if automatic
            else f"{session.created_by} opened '{bounded_text(session.objective, 200)}' on "
            f"{session.chip_id}"
        ),
        actor=session.created_by,
        # An automatic session was created by QDash for the run, not stated by a person.
        actor_kind="server" if automatic else "human",
        provenance="server_record",
        data={
            "objective": session.objective,
            "chip_id": session.chip_id,
            "origin": session.origin.value,
        },
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
        _run_events(records, run, run.run_id in cited_runs, add)

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


def _run_events(
    records: CalibrationAuditRecords, run: CalibrationPipelineRunDocument, cited: bool, add: Any
) -> None:
    """A run's request, its dispatch, and a measurement per step execution of the run."""
    origin = run.reported_origin
    agent_tool = origin is not None and origin.source == "agent_tool"
    missing: list[str] = []
    kind = run.run_kind
    # Only a pipeline run is requested with a spec; other kinds have none to record.
    if run.spec is None and kind == CalibrationRunKind.PIPELINE:
        missing.append("requested_spec")
    if agent_tool:
        missing.append("host_approval")
        if run.decision_id is None:
            missing.append("decision")
    run_label = run.run_name or run.pipeline_name or run.run_id
    trigger_text = "a scheduled" if run.trigger == CalibrationRunTrigger.SCHEDULE else "an"
    add(
        event_id=f"pipeline_requested:{run.run_id}",
        at=run.requested_at,
        kind="pipeline_requested",
        summary=(
            (
                f"{run.requested_by} requested {kind.value.replace('_', ' ')} '{run_label}'"
                if run.trigger == CalibrationRunTrigger.API
                else f"The worker recorded {trigger_text} {kind.value.replace('_', ' ')} "
                f"'{run_label}' for {run.requested_by}"
            )
            + (f" for decision {run.decision_id}" if run.decision_id else "")
            + (f" (reported: {origin.tool})" if origin else "")
        ),
        actor=run.requested_by,
        actor_kind=(
            "agent"
            if agent_tool
            else "unknown"
            if run.trigger == CalibrationRunTrigger.API
            else "server"
        ),
        provenance="server_record",
        pipeline_run_id=run.run_id,
        decision_id=run.decision_id,
        missing=missing,
        data={
            "run_kind": kind.value,
            "run_name": run.run_name or run.pipeline_name,
            "trigger": run.trigger.value,
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
        summary=f"Dispatch of {run_label}: {dispatch.value}",
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
                "tasks": [task_facts(t) for t in tasks[:MAX_TASKS_PER_EVENT]],
                "omitted_tasks": max(0, len(tasks) - MAX_TASKS_PER_EVENT),
            },
        )
