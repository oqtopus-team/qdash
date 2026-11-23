"""Launch a saved workflow or a single task as a run of a calibration session.

Every launch path the API offers records its run before the flow run is created, in the
session the request names or in an automatic session created for it, so the worker can stamp
the session and run on every step execution. A pipeline launch does the same through its own
router, which also records decisions and the requested spec.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from qdash.api.schemas.flow import ExecuteFlowResponse
from qdash.api.services.calibration_session_service import run_request_hash

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from qdash.api.services.calibration_session_service import CalibrationSessionService
    from qdash.datamodel.calibration_session import CalibrationRunIdentity, CalibrationRunKind


async def launch_run(
    sessions: CalibrationSessionService,
    *,
    project_id: str,
    username: str,
    chip_id: str,
    kind: CalibrationRunKind,
    run_name: str,
    request: dict[str, Any],
    calibration_session_id: str | None,
    idempotency_key: str | None,
    validate: Callable[[], Any],
    dispatch: Callable[[Any, CalibrationRunIdentity | None], Awaitable[ExecuteFlowResponse]],
) -> ExecuteFlowResponse:
    """Record and launch one run, returning the launch response with its session and run.

    A request whose chip QDash cannot tell before the launch (a saved flow with no
    ``chip_id`` parameter and no saved chip) cannot be recorded against one. Without
    ``calibration_session_id`` or ``idempotency_key`` it is launched without an identity, and
    the worker records it in an automatic session on the chip it calibrates when it starts.
    With either, it is refused before anything is launched: neither the session nor the
    replay by key could be honored, and QDash never guesses the chip.
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

    recorded = await sessions.launch(
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
    )
    return ExecuteFlowResponse.model_validate(
        {
            **recorded.response,
            "calibration_session_id": recorded.calibration_session_id,
            "calibration_run_id": recorded.run_id,
            "replayed": recorded.replayed,
        }
    )
