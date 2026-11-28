"""The current state of one run's whole flow run, read from its record and Prefect.

A run's state is decided on every read and never cached: a dispatched run bound to a flow run
is read from Prefect in the same request (one flow run, with the lifecycle reader's bounded
timeout), so a flow run restarted or resumed after an earlier read ended is reported running
again. ``RunDocument.flow_end_state``, recorded by the automatic-session lifecycle for display,
is never trusted here, and neither is any step execution: the first step completing says
nothing about the steps after it.

Reading a run's state changes nothing: no session is checked or closed, and nothing is
recorded on the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 - dataclass field type
from typing import TYPE_CHECKING

from qdash.api.services import calibration_session_lifecycle as lifecycle
from qdash.api.services.run_ledger import dispatch_status
from qdash.common.utils.datetime import now
from qdash.datamodel.run import RunDispatchStatus, RunFlowEndState, RunFlowStatus

if TYPE_CHECKING:
    from qdash.dbmodel.run import RunDocument

logger = logging.getLogger("uvicorn.app")

_TERMINAL = {
    RunFlowEndState.COMPLETED: RunFlowStatus.COMPLETED,
    RunFlowEndState.FAILED: RunFlowStatus.FAILED,
    RunFlowEndState.CANCELLED: RunFlowStatus.CANCELLED,
    RunFlowEndState.CRASHED: RunFlowStatus.CRASHED,
}


@dataclass(frozen=True)
class FlowObservation:
    """What one read found for a run's whole flow run."""

    status: RunFlowStatus
    observed_at: datetime
    reason: str = ""
    prefect_state: str | None = None
    end_state: RunFlowEndState | None = None


def observe_run_flow(run: RunDocument) -> FlowObservation:
    """The run's whole flow run state now; Prefect is read only for a launched run.

    A Prefect read that fails or times out is ``unavailable``; a flow run Prefect does not
    report is ``unknown``. Neither is ever reported as running or ended.
    """
    observed_at = now()
    state = dispatch_status(run)
    if state == RunDispatchStatus.DISPATCHING:
        return FlowObservation(
            RunFlowStatus.DISPATCHING, observed_at, "QDash is still launching the run"
        )
    if state == RunDispatchStatus.REJECTED:
        return FlowObservation(
            RunFlowStatus.NOT_LAUNCHED,
            observed_at,
            "QDash refused the launch; no flow run was created",
        )
    if state == RunDispatchStatus.UNKNOWN:
        return FlowObservation(
            RunFlowStatus.UNKNOWN,
            observed_at,
            "The launch outcome is unknown; the run may have started",
        )
    if not run.flow_run_id:
        return FlowObservation(
            RunFlowStatus.UNKNOWN, observed_at, "No flow run was recorded for the run"
        )
    flow_run_id = str(run.flow_run_id)
    try:
        # Resolved at call time, so tests replace the lifecycle's reader in one place.
        states = lifecycle.read_prefect_flow_states([flow_run_id])
    except Exception:
        logger.warning("Reading flow run %s of run %s failed", flow_run_id, run.run_id)
        return FlowObservation(
            RunFlowStatus.UNAVAILABLE,
            now(),
            f"Prefect could not be read for flow run {flow_run_id}",
        )
    observed_at = now()
    if flow_run_id not in states:
        return FlowObservation(
            RunFlowStatus.UNKNOWN,
            observed_at,
            f"Prefect does not report flow run {flow_run_id}",
        )
    prefect_state = str(states[flow_run_id] or "").upper() or None
    if prefect_state is None:
        return FlowObservation(
            RunFlowStatus.UNKNOWN,
            observed_at,
            f"Prefect reports flow run {flow_run_id} without a state",
        )
    end = lifecycle.TERMINAL_PREFECT_STATES.get(prefect_state)
    if end is None:
        return FlowObservation(
            RunFlowStatus.RUNNING,
            observed_at,
            f"Prefect reports flow run {flow_run_id} {prefect_state.lower()}",
            prefect_state=prefect_state,
        )
    return FlowObservation(
        _TERMINAL[end],
        observed_at,
        f"Prefect reports flow run {flow_run_id} {prefect_state.lower()}",
        prefect_state=prefect_state,
        end_state=end,
    )


__all__ = ["FlowObservation", "observe_run_flow"]
