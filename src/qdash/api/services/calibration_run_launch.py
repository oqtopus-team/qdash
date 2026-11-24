"""Launch a saved workflow or a single task as a run.

Every launch path the API offers records its run before the flow run is created, so the
worker can stamp the run (and its calibration session, if it has one) on every step
execution. The run joins the session the request names, or an automatic session when it names
none. A pipeline launch does the same through its own router, which also
records decisions and the requested spec.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.services.run_ledger import RunLedger, run_request_hash

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from qdash.api.services.calibration_session_service import CalibrationSessionService
    from qdash.datamodel.run import RunIdentity, RunKind


async def launch_run(
    sessions: CalibrationSessionService,
    *,
    project_id: str,
    username: str,
    chip_id: str,
    kind: RunKind,
    run_name: str,
    request: dict[str, Any],
    calibration_session_id: str | None,
    idempotency_key: str | None,
    validate: Callable[[], Any],
    dispatch: Callable[[Any, RunIdentity | None], Awaitable[ExecuteFlowResponse]],
    preflight: Callable[[Any], None] | None = None,
) -> ExecuteFlowResponse:
    """Record and launch one run, returning the launch response with its run and session.

    A request whose chip QDash cannot tell before the launch (a saved flow with no
    ``chip_id`` parameter and no saved chip) cannot be recorded against one. Without
    ``calibration_session_id`` or ``idempotency_key`` it is launched without an identity, and
    the worker records its run on the chip it calibrates when it starts.
    With either, it is refused before anything is launched: neither the session nor the
    replay by key could be honored, and QDash never guesses the chip.

    ``preflight`` refuses a validated request before anything is recorded (see
    ``RunLedger.launch``); a run without a chip claims no hardware, so it is not checked.
    """
    if not chip_id:
        if calibration_session_id is not None or idempotency_key is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{run_name or 'This run'} names no chip (no chip_id parameter and no chip "
                    "saved with the flow), so QDash cannot record it in a calibration session "
                    "or replay it by idempotency key. Nothing was started. Pass "
                    "parameters.chip_id, or save the flow with a chip, to use "
                    "calibration_session_id or idempotency_key."
                ),
            )
        validated = validate()
        return await dispatch(validated, None)

    recorded = await RunLedger(sessions).launch(
        project_id=project_id,
        username=username,
        chip_id=chip_id,
        kind=kind,
        run_name=run_name,
        request_hash=run_request_hash(kind, chip_id, request),
        calibration_session_id=calibration_session_id,
        idempotency_key=idempotency_key,
        validate=validate,
        dispatch=dispatch,
        response=lambda _validated, dispatched: dispatched.model_dump(mode="json"),
        preflight=preflight,
    )
    return ExecuteFlowResponse.model_validate(
        {
            **recorded.response,
            "calibration_session_id": recorded.calibration_session_id,
            "calibration_run_id": recorded.run_id,
            "replayed": recorded.replayed,
        }
    )
