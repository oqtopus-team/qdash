"""Schemas for the cool-down wiring change history (checkpoints).

Kept separate from ``cooldown.py`` so this feature can be lifted out (e.g. into
a dedicated ``cryowire`` package) without touching cool-down core types.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class CooldownWiringCheckpointRequest(BaseModel):
    """Body for recording a wiring change checkpoint within a cool-down."""

    comment: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Why the wiring changed at this point in time",
    )


class CooldownWiringEventResponse(BaseModel):
    """One wiring-history entry for a cool-down."""

    id: str
    cooldown_id: str
    actor_user_id: str | None = None
    actor: str
    action: str
    comment: str
    wiring_info_snapshot: str
    block_count: int
    image_count: int
    created_at: datetime


class ListCooldownWiringEventsResponse(BaseModel):
    events: list[CooldownWiringEventResponse]
