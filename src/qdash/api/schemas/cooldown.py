"""Schemas for cool-down endpoints."""

from datetime import datetime

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


class CooldownResponse(BaseModel):
    """Single cool-down record."""

    cooldown_id: str
    cryo_id: str
    description: str
    started_at: datetime
    ended_at: datetime | None
    chip_ids: list[str]
    note: NoteModel = Field(default_factory=NoteModel)


class ListCooldownsResponse(BaseModel):
    cooldowns: list[CooldownResponse]
