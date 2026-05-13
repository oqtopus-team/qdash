"""Schemas for cool-down endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from qdash.datamodel.note import NoteModel


class CooldownCreateRequest(BaseModel):
    """Body for creating a cool-down."""

    cooldown_id: str = Field(
        ..., max_length=100, description="Project-unique identifier (e.g. '2026-001')"
    )
    cryo_id: str = Field(..., description="Cryostat the cool-down belongs to")
    description: str = Field(default="", max_length=2000)
    started_at: datetime
    ended_at: datetime | None = None
    chip_ids: list[str] = Field(default_factory=list)


class CooldownUpdateRequest(BaseModel):
    """Body for updating a cool-down. All fields optional."""

    description: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    wiring_info: str | None = Field(
        default=None,
        description="Markdown export of the wiring document (derived from wiring_blocks)",
    )
    wiring_blocks: list[dict[str, Any]] | None = Field(
        default=None,
        description="BlockNote document JSON. Source of truth when present.",
    )


class CooldownResponse(BaseModel):
    """Single cool-down record."""

    cooldown_id: str
    cryo_id: str
    description: str
    started_at: datetime
    ended_at: datetime | None
    chip_ids: list[str]
    note: NoteModel = Field(default_factory=NoteModel)
    wiring_info: str = Field(default="")
    wiring_blocks: list[dict[str, Any]] = Field(default_factory=list)


class ListCooldownsResponse(BaseModel):
    cooldowns: list[CooldownResponse]
