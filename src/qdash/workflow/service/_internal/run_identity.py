"""The calibration session and run a flow run's step executions are recorded in.

The owner of each step execution stamps ``calibration_session_id`` and
``calibration_run_id`` into the execution note, before the execution is first written.
The identity is read once per flow run:

- A flow run the API launched names its run, with the dispatch token of its launch, in the
  flow-run context. The worker checks that the run is recorded in the project, on the chip,
  in the session named, and for the user the flow run runs as, and binds the flow run to it
  only when it is already bound to this flow run or the token matches and no other flow run
  holds it (see ``adopt_recorded_run``).
- A flow run without one (a cron or one-time schedule, or a run started in Prefect directly)
  is recorded by the worker in an automatic session of its own, with IDs derived from the
  flow run, so every step and every retry of the flow run reaches the same records.

A failure to resolve the identity fails the step before any hardware is used: a run whose
history cannot be grouped is not started. Outside a Prefect flow run (a local script or a
test) there is no run to group, and nothing is stamped.
"""

from __future__ import annotations

import logging
from typing import Any

from qdash.datamodel.calibration_session import CALIBRATION_RUN_CONTEXT_KEY

logger = logging.getLogger(__name__)

# Identity of each flow run this process resolved, with the project, chip and owner it was resolved
# for: every step of a pipeline, and every CalibService run of one flow, shares it. ``None``
# marks a run left without a session.
_resolved: dict[str, tuple[str, str, str, dict[str, str] | None]] = {}


def _flow_run_context() -> tuple[Any, Any] | None:
    try:
        from prefect.context import FlowRunContext
    except ImportError:
        return None
    context = FlowRunContext.get()
    if context is None or context.flow_run is None:
        return None
    return context.flow_run, getattr(context, "flow", None)


def calibration_note(
    *, project_id: str, chip_id: str, username: str, run_name: str | None
) -> dict[str, str]:
    """The note keys naming this flow run's calibration session and run; empty outside one."""
    from qdash.repository.calibration_run import (
        NOTE_RUN_KEY,
        NOTE_SESSION_KEY,
        UNGROUPED_MARKER,
        CalibrationRunMismatch,
        adopt_recorded_run,
        read_identity,
        record_worker_run,
    )

    found = _flow_run_context()
    if found is None:
        return {}
    flow_run, flow = found
    raw_id = getattr(flow_run, "id", None)
    if raw_id is None:
        return {}
    flow_run_id = str(raw_id)
    if flow_run_id in _resolved:
        cached_project, cached_chip, cached_username, cached = _resolved[flow_run_id]
        if (cached_project, cached_chip) != (project_id, chip_id):
            raise CalibrationRunMismatch(
                f"Flow run {flow_run_id} is recorded as a calibration run on chip "
                f"{cached_chip}; it cannot also calibrate chip {chip_id}"
            )
        if cached_username != username:
            raise CalibrationRunMismatch(
                f"Flow run {flow_run_id} cannot change its recorded owner between steps"
            )
        return dict(cached) if cached else {}

    value = (getattr(flow_run, "context", None) or {}).get(CALIBRATION_RUN_CONTEXT_KEY)
    if isinstance(value, dict) and value.get(UNGROUPED_MARKER):
        _resolved[flow_run_id] = (project_id, chip_id, username, None)
        return {}
    identity = read_identity(value)
    if identity is not None:
        identity = adopt_recorded_run(
            identity,
            project_id=project_id,
            chip_id=chip_id,
            username=username,
            flow_run_id=flow_run_id,
        )
    else:
        identity = record_worker_run(
            project_id=project_id,
            chip_id=chip_id,
            username=username,
            flow_run_id=flow_run_id,
            flow_name=getattr(flow, "name", None),
            run_name=run_name or str(getattr(flow_run, "name", "") or ""),
            auto_scheduled=bool(getattr(flow_run, "auto_scheduled", False)),
        )
        logger.info(
            "Recorded flow run %s as calibration run %s in session %s",
            flow_run_id,
            identity.run_id,
            identity.calibration_session_id,
        )
    note = {
        NOTE_SESSION_KEY: identity.calibration_session_id,
        NOTE_RUN_KEY: identity.run_id,
    }
    _resolved[flow_run_id] = (project_id, chip_id, username, note)
    return dict(note)
