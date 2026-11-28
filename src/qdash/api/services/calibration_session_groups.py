"""Which executions and agent sessions of one chip a calibration session row of the list holds.

The grouped Execution list shows a calibration session as the display parent of the work
started in it. Membership comes only from the explicit records the links module reads:

- a ``CalibrationPipelineRunDocument`` of the session, on the chip, whose ``run_id`` is an
  execution's ``note.calibration_run_id`` (stamped by the worker), or, for a run recorded
  before that note existed, whose flow run is the execution's ``note.flow_run_id``; a flow run
  that more than one run claims groups nothing. An agent action's run is left to its agent
  session, which holds the execution;
- an agent session admitted to the session (``calibration_admission`` ``admitted``) on the
  same chip. The agent session stays a group of its own executions, nested in the row.

An execution an agent session's action holds stays with that agent session, so no execution is
listed twice. Nothing is grouped by chip, time, tag, name, or chat, and no record is written.
The whole chip is read in three bounded queries (sessions, runs, step executions), whatever
the number of rows, so the list can group before it pages.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from qdash.api.services.agent_execution_links import utc
from qdash.api.services.calibration_session_links import admitted_parent
from qdash.datamodel.calibration_session import CalibrationRunKind
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.execution_history import ExecutionHistoryDocument

if TYPE_CHECKING:
    from qdash.api.services.agent_execution_links import ChipLinks


@dataclass(frozen=True)
class RunExecution:
    """One step execution of a pipeline run, as the list needs it."""

    execution_id: str
    run_id: str
    status: str
    start_at: datetime | None
    end_at: datetime | None


@dataclass
class ChipCalibrationGroups:
    """The calibration sessions of one chip and what each groups."""

    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Runs of each session, oldest request first (every status, as recorded).
    runs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # Step executions of each run, oldest first.
    run_executions: dict[str, list[RunExecution]] = field(default_factory=dict)
    # Execution -> calibration session, for the step executions the rows hold.
    execution_session: dict[str, str] = field(default_factory=dict)
    # Admitted agent session -> calibration session.
    agent_parent: dict[str, str] = field(default_factory=dict)
    # Calibration session -> nested agent sessions, oldest first.
    agents: dict[str, list[str]] = field(default_factory=dict)


_RUN_FIELDS = {
    "_id": 0,
    "run_id": 1,
    "calibration_session_id": 1,
    "flow_run_id": 1,
    "status": 1,
    "pipeline_name": 1,
    "run_kind": 1,
    "run_name": 1,
    "trigger": 1,
    "requested_by": 1,
    "requested_at": 1,
    "updated_at": 1,
    "reported_origin": 1,
    "response.targets": 1,
    "decision_id": 1,
}


def resolve_chip_calibration_groups(
    project_id: str, chip_id: str, links: ChipLinks
) -> ChipCalibrationGroups:
    """Every calibration session of the chip with its runs, step executions, and agents."""
    groups = ChipCalibrationGroups()
    for doc in CalibrationSessionDocument.get_motor_collection().find(
        {"project_id": project_id, "chip_id": chip_id},
        {
            "_id": 0,
            "calibration_session_id": 1,
            "chip_id": 1,
            "objective": 1,
            "status": 1,
            "origin": 1,
            "created_by": 1,
            "created_at": 1,
            "closed_at": 1,
        },
    ):
        groups.sessions[str(doc["calibration_session_id"])] = doc
    if not groups.sessions:
        return groups

    for session_id in sorted(links.session_created, key=lambda s: (links.session_created[s], s)):
        parent = admitted_parent(links.session_info.get(session_id, {}))
        if parent is not None and parent in groups.sessions:
            groups.agent_parent[session_id] = parent
            groups.agents.setdefault(parent, []).append(session_id)

    runs = list(
        CalibrationPipelineRunDocument.get_motor_collection().find(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "calibration_session_id": {"$in": sorted(groups.sessions)},
                "run_kind": {"$ne": CalibrationRunKind.AGENT_ACTION.value},
            },
            _RUN_FIELDS,
        )
    )
    runs.sort(key=lambda run: (utc(run.get("requested_at")) or datetime.min, run["run_id"]))
    claims = Counter(str(run["flow_run_id"]) for run in runs if run.get("flow_run_id"))
    by_flow: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for run in runs:
        groups.runs.setdefault(str(run["calibration_session_id"]), []).append(run)
        by_id[str(run["run_id"])] = run
        flow_run_id = run.get("flow_run_id")
        # A flow run two records claim belongs to neither: shown as ordinary executions.
        if flow_run_id and claims[str(flow_run_id)] == 1:
            by_flow[str(flow_run_id)] = run
    if not by_id:
        return groups

    clauses: list[dict[str, Any]] = [{"note.calibration_run_id": {"$in": sorted(by_id)}}]
    if by_flow:
        clauses.append(
            {
                "note.flow_run_id": {"$in": sorted(by_flow)},
                "note.calibration_run_id": {"$exists": False},
            }
        )
    found: dict[str, list[RunExecution]] = defaultdict(list)
    for doc in ExecutionHistoryDocument.get_motor_collection().find(
        {"project_id": project_id, "chip_id": chip_id, "$or": clauses},
        {
            "_id": 0,
            "execution_id": 1,
            "status": 1,
            "start_at": 1,
            "end_at": 1,
            "note.flow_run_id": 1,
            "note.calibration_run_id": 1,
        },
    ):
        execution_id = str(doc["execution_id"])
        if execution_id in links.by_execution:
            # Held by an agent session's action: it stays in that group.
            continue
        note = doc.get("note") or {}
        # The stamp names the run; only an execution without one is found by its flow run.
        stamp = note.get("calibration_run_id")
        run = by_id.get(str(stamp)) if stamp else by_flow.get(str(note.get("flow_run_id") or ""))
        if run is None:
            continue
        found[str(run["run_id"])].append(
            RunExecution(
                execution_id=execution_id,
                run_id=str(run["run_id"]),
                status=str(doc.get("status") or ""),
                start_at=utc(doc.get("start_at")),
                end_at=utc(doc.get("end_at")),
            )
        )
        groups.execution_session[execution_id] = str(run["calibration_session_id"])
    for run_id, executions in found.items():
        executions.sort(
            key=lambda e: (e.start_at or datetime.min.replace(tzinfo=None), e.execution_id)
        )
        groups.run_executions[run_id] = executions
    return groups
