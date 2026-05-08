"""Cool-down wiring change history (checkpoints) router.

Kept separate from ``routers/cooldown.py`` so this feature can be lifted out
(e.g. into a dedicated ``cryowire`` package) without touching the cool-down
core router. The URL prefix is intentionally nested under ``/cooldowns/{id}``
because a checkpoint is always scoped to one cool-down.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from qdash.api.dependencies import get_cooldown_wiring_event_service  # noqa: TCH002
from qdash.api.lib.project import (  # noqa: TCH002
    ProjectContext,
    get_project_context,
    get_project_context_editor,
)
from qdash.api.schemas.cooldown_wiring_event import (
    CooldownWiringCheckpointRequest,
    CooldownWiringEventResponse,
    ListCooldownWiringEventsResponse,
)
from qdash.api.services.cooldown_wiring_event_service import (  # noqa: TCH002
    CooldownWiringEventService,
)

router = APIRouter()


@router.post(
    "/cooldowns/{cooldown_id}/wiring-checkpoint",
    summary="Record a wiring change checkpoint within a cool-down",
    operation_id="createCooldownWiringCheckpoint",
    response_model=CooldownWiringEventResponse,
    status_code=201,
)
def create_wiring_checkpoint(
    cooldown_id: str,
    body: CooldownWiringCheckpointRequest,
    ctx: Annotated[ProjectContext, Depends(get_project_context_editor)],
    service: Annotated[CooldownWiringEventService, Depends(get_cooldown_wiring_event_service)],
) -> CooldownWiringEventResponse:
    return service.create_checkpoint(
        project_id=ctx.project_id,
        cooldown_id=cooldown_id,
        comment=body.comment,
        actor=ctx.user.username,
    )


@router.get(
    "/cooldowns/{cooldown_id}/wiring-events",
    summary="List wiring change history for a cool-down",
    operation_id="listCooldownWiringEvents",
    response_model=ListCooldownWiringEventsResponse,
)
def list_wiring_events(
    cooldown_id: str,
    ctx: Annotated[ProjectContext, Depends(get_project_context)],
    service: Annotated[CooldownWiringEventService, Depends(get_cooldown_wiring_event_service)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    skip: Annotated[int, Query(ge=0)] = 0,
) -> ListCooldownWiringEventsResponse:
    return service.list_events(
        project_id=ctx.project_id, cooldown_id=cooldown_id, limit=limit, skip=skip
    )
