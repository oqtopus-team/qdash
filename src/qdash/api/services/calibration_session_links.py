"""Which calibration session an execution belongs to, and the origin its launch reported.

A calibration session never owns an execution through a tag, a name, the chip, or the time.
Two server records relate one, and this module reads only those:

- A pipeline run recorded in the session (``CalibrationPipelineRunDocument``) whose flow run
  is the execution's ``note.flow_run_id``, on the execution's chip. Every step execution of
  the run is then a member.
- An agent session admitted to the session (``calibration_admission`` ``admitted``) whose
  action dispatched the execution, as ``agent_execution_links`` resolves it. A session that is
  pending or rejected never operated, so it relates nothing.

The session itself must exist in the request's project and be on the execution's chip. When
the records name different sessions, or more than one pipeline run claims a flow run, the
execution belongs to none: the reader shows it as an ordinary execution rather than guess.

The origin is the ``PipelineLaunchDocument`` of the execution's flow run: what the caller
reported, never verified. It says nothing about membership, and membership says nothing about
who ran an execution.

Every read is batched over the executions passed in: at most four queries, whatever their
number, so a list page costs the same as one execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qdash.api.schemas.execution import (
    CalibrationSessionRef,
    ExecutionAgentSessionLink,
    ExecutionCalibrationSessionLink,
)
from qdash.datamodel.calibration_session import CalibrationAdmission, CalibrationSessionStatus
from qdash.datamodel.launch_origin import ReportedLaunchOrigin
from qdash.dbmodel.agent_session import AgentSessionDocument
from qdash.dbmodel.calibration_session import (
    CalibrationPipelineRunDocument,
    CalibrationSessionDocument,
)
from qdash.dbmodel.pipeline_launch import PipelineLaunchDocument

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from qdash.dbmodel.execution_history import ExecutionHistoryDocument


@dataclass(frozen=True)
class ExecutionRelations:
    """What QDash's records relate one execution to, beyond its own row."""

    calibration_session: ExecutionCalibrationSessionLink | None = None
    reported_origin: ReportedLaunchOrigin | None = None


NO_RELATIONS = ExecutionRelations()


def _flow_run_id(execution: ExecutionHistoryDocument) -> str | None:
    value = (execution.note or {}).get("flow_run_id")
    return value if isinstance(value, str) and value else None


def calibration_session_refs(
    project_id: str, calibration_session_ids: Iterable[str]
) -> dict[str, CalibrationSessionRef]:
    """The project's calibration sessions with these IDs, in one query."""
    wanted = sorted({value for value in calibration_session_ids if value})
    if not wanted:
        return {}
    return {
        str(doc["calibration_session_id"]): CalibrationSessionRef(
            calibration_session_id=str(doc["calibration_session_id"]),
            chip_id=str(doc["chip_id"]),
            objective=str(doc.get("objective") or ""),
            status=CalibrationSessionStatus(str(doc["status"])),
        )
        for doc in CalibrationSessionDocument.get_motor_collection().find(
            {"project_id": project_id, "calibration_session_id": {"$in": wanted}},
            {"_id": 0, "calibration_session_id": 1, "chip_id": 1, "objective": 1, "status": 1},
        )
    }


def admitted_parent(session: Any) -> str | None:
    """The calibration session an agent session record was admitted to, or None.

    Accepts a session document or a projection of one. Only ``admitted`` counts: a pending
    session waits for its start to be finalized and a rejected one never operates.
    """
    get = session.get if isinstance(session, dict) else lambda key: getattr(session, key, None)
    parent = get("calibration_session_id")
    admission = get("calibration_admission")
    if not parent or admission is None:
        return None
    return str(parent) if str(admission) == CalibrationAdmission.ADMITTED.value else None


def agent_session_parents(
    project_id: str, sessions: Iterable[AgentSessionDocument]
) -> dict[str, CalibrationSessionRef]:
    """Each admitted agent session's calibration session, on the same chip, in one query."""
    listed = list(sessions)
    parents = {s.session_id: admitted_parent(s) for s in listed}
    refs = calibration_session_refs(project_id, (p for p in parents.values() if p))
    found: dict[str, CalibrationSessionRef] = {}
    for session in listed:
        parent = parents.get(session.session_id)
        ref = refs.get(parent) if parent else None
        if ref is not None and ref.chip_id == session.chip_id:
            found[session.session_id] = ref
    return found


def resolve_execution_relations(
    project_id: str,
    executions: Iterable[ExecutionHistoryDocument],
    agent_links: Mapping[str, ExecutionAgentSessionLink | None] | None = None,
) -> dict[str, ExecutionRelations]:
    """Relations of each execution, keyed by execution ID; one with none is left out.

    ``agent_links`` holds the agent session link already resolved for each execution; only a
    verified one (``linked``) is followed.
    """
    rows = [e for e in executions if e.execution_id]
    if not rows:
        return {}
    links = agent_links or {}
    flow_run_ids = sorted({fr for e in rows if (fr := _flow_run_id(e)) is not None})

    runs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    origins: dict[tuple[str, str], list[ReportedLaunchOrigin]] = {}
    if flow_run_ids:
        for doc in CalibrationPipelineRunDocument.get_motor_collection().find(
            {"project_id": project_id, "flow_run_id": {"$in": flow_run_ids}},
            {"_id": 0, "run_id": 1, "calibration_session_id": 1, "chip_id": 1, "flow_run_id": 1},
        ):
            runs.setdefault((str(doc["chip_id"]), str(doc["flow_run_id"])), []).append(doc)
        for doc in PipelineLaunchDocument.get_motor_collection().find(
            {"project_id": project_id, "flow_run_id": {"$in": flow_run_ids}},
            {"_id": 0, "chip_id": 1, "flow_run_id": 1, "reported_origin": 1},
        ):
            try:
                origin = ReportedLaunchOrigin.model_validate(doc.get("reported_origin"))
            except ValueError:
                continue
            origins.setdefault((str(doc["chip_id"]), str(doc["flow_run_id"])), []).append(origin)

    agent_ids = sorted(
        {
            link.session_id
            for link in links.values()
            if link is not None and link.linked and link.session_id
        }
    )
    agents: dict[str, dict[str, Any]] = {}
    if agent_ids:
        agents = {
            str(doc["session_id"]): doc
            for doc in AgentSessionDocument.get_motor_collection().find(
                {"project_id": project_id, "session_id": {"$in": agent_ids}},
                {
                    "_id": 0,
                    "session_id": 1,
                    "chip_id": 1,
                    "calibration_session_id": 1,
                    "calibration_admission": 1,
                },
            )
        }

    # (calibration session, via, child id) candidates of each execution.
    candidates: dict[str, list[tuple[str, str, str]]] = {}
    for execution in rows:
        found: list[tuple[str, str, str]] = []
        flow_run_id = _flow_run_id(execution)
        if flow_run_id is not None:
            for run in runs.get((execution.chip_id, flow_run_id), []):
                found.append(
                    (str(run["calibration_session_id"]), "pipeline_run", str(run["run_id"]))
                )
        link = links.get(execution.execution_id)
        agent = agents.get(link.session_id) if link is not None and link.linked else None
        if agent is not None and agent.get("chip_id") == execution.chip_id:
            parent = admitted_parent(agent)
            if parent is not None:
                found.append((parent, "agent_session", str(agent["session_id"])))
        if found:
            candidates[execution.execution_id] = found
    refs = calibration_session_refs(
        project_id, (cs for found in candidates.values() for cs, _, _ in found)
    )

    relations: dict[str, ExecutionRelations] = {}
    for execution in rows:
        membership: ExecutionCalibrationSessionLink | None = None
        found = candidates.get(execution.execution_id, [])
        # One record of each kind at most, all naming one session; anything else is ambiguous.
        vias = [via for _, via, _ in found]
        if found and len({cs for cs, _, _ in found}) == 1 and len(vias) == len(set(vias)):
            calibration_session_id = found[0][0]
            ref = refs.get(calibration_session_id)
            if ref is not None and ref.chip_id == execution.chip_id:
                run_id = next((child for _, via, child in found if via == "pipeline_run"), None)
                agent_id = next((child for _, via, child in found if via == "agent_session"), None)
                membership = ExecutionCalibrationSessionLink(
                    **ref.model_dump(),
                    via="pipeline_run" if run_id is not None else "agent_session",
                    pipeline_run_id=run_id,
                    agent_session_id=agent_id,
                )
        flow_run_id = _flow_run_id(execution)
        reported = origins.get((execution.chip_id, flow_run_id), []) if flow_run_id else []
        single = reported[0] if len(reported) == 1 else None
        if membership is not None or single is not None:
            relations[execution.execution_id] = ExecutionRelations(
                calibration_session=membership, reported_origin=single
            )
    return relations
