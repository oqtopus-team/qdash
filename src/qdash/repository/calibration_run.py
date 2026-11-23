"""Automatic calibration sessions, the grouping QDash gives runs that name no session.

The run ledger itself (recording, binding, and the worker's checks) is
``qdash.repository.run_ledger``; the names it had here are re-exported below. This module only
creates or loads the automatic session a run or agent session joins when it names none. The
session is a record of purpose: a run's guarantees never depend on it.
"""

from __future__ import annotations

from pymongo.errors import DuplicateKeyError

from qdash.common.utils.datetime import now
from qdash.datamodel.calibration_session import CalibrationSessionOrigin
from qdash.datamodel.run import CalibrationRunKind
from qdash.dbmodel.calibration_session import CalibrationSessionDocument
from qdash.repository.run_ledger import (
    NOTE_RUN_KEY,
    NOTE_SESSION_KEY,
    SYSTEM_FLOW_KINDS,
    UNGROUPED_MARKER,
    RunMismatch,
    bind_flow_run,
    digest,
    read_identity,
    record_worker_run,
    run_id_for_flow_run,
    run_kind_of_flow,
)

# Earlier names, kept for callers of this module.
CalibrationRunMismatch = RunMismatch
adopt_recorded_run = bind_flow_run
_digest = digest

__all__ = [
    "NOTE_RUN_KEY",
    "NOTE_SESSION_KEY",
    "SYSTEM_FLOW_KINDS",
    "UNGROUPED_MARKER",
    "CalibrationRunMismatch",
    "adopt_recorded_run",
    "automatic_objective",
    "automatic_session_id_for_flow_run",
    "automatic_session_id_for_key",
    "insert_or_load_automatic_session",
    "read_identity",
    "record_worker_run",
    "run_id_for_flow_run",
    "run_kind_of_flow",
]


def automatic_session_id_for_key(project_id: str, username: str, idempotency_key: str) -> str:
    """The automatic session of a request's idempotency key: the same on every retry."""
    return f"cs-auto-{_digest(project_id, username, idempotency_key)}"


def automatic_session_id_for_flow_run(flow_run_id: str) -> str:
    """The automatic session the worker records for a flow run QDash did not launch."""
    return f"cs-flow-{flow_run_id}"


def automatic_objective(kind: CalibrationRunKind, run_name: str) -> str:
    """The objective text of an automatic session: what its first run launched."""
    label = {
        CalibrationRunKind.PIPELINE: "Pipeline",
        CalibrationRunKind.WORKFLOW: "Workflow",
        CalibrationRunKind.TASK: "Task",
        CalibrationRunKind.AGENT_ACTION: "Agent session",
    }[kind]
    return f"{label} {run_name}".strip() if run_name else label


def insert_or_load_automatic_session(
    *,
    calibration_session_id: str,
    project_id: str,
    chip_id: str,
    username: str,
    objective: str,
    child_count: int = 0,
) -> CalibrationSessionDocument:
    """Insert an automatic session, or load the one an earlier attempt inserted.

    The ID is derived from the request's key or the flow run, so a retry reaches the same
    session. One found with that ID must be an automatic session of the same project, chip,
    and user; anything else is refused rather than reused.
    """
    timestamp = now()
    doc = CalibrationSessionDocument(
        calibration_session_id=calibration_session_id,
        project_id=project_id,
        chip_id=chip_id,
        objective=objective,
        created_by=username,
        origin=CalibrationSessionOrigin.AUTOMATIC,
        child_count=child_count,
        created_at=timestamp,
        updated_at=timestamp,
    )
    try:
        doc.insert()
        return doc
    except DuplicateKeyError:
        existing = CalibrationSessionDocument.find_one(
            {"calibration_session_id": calibration_session_id}
        ).run()
    if existing is None:
        raise CalibrationRunMismatch(
            f"Calibration session {calibration_session_id} could not be recorded or read"
        )
    if (
        existing.project_id != project_id
        or existing.chip_id != chip_id
        or existing.created_by != username
        or existing.origin != CalibrationSessionOrigin.AUTOMATIC
    ):
        raise CalibrationRunMismatch(
            f"Calibration session {calibration_session_id} belongs to another project, chip, "
            "or user"
        )
    return existing
