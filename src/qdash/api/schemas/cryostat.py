"""Schemas for cryostat endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from qdash.datamodel.note import NoteModel


class CryostatCreateRequest(BaseModel):
    """Body for creating a cryostat."""

    cryo_id: str = Field(..., max_length=100, description="Project-unique identifier")
    name: str = Field(default="", max_length=200)
    manufacturer: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    status: str = Field(default="active", description="active | maintenance | decommissioned")
    commissioned_at: datetime | None = None


class CryostatUpdateRequest(BaseModel):
    """Body for updating a cryostat. All fields optional."""

    name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    location: str | None = None
    status: str | None = None
    commissioned_at: datetime | None = None
    decommissioned_at: datetime | None = None


class CryostatResponse(BaseModel):
    """Single cryostat record."""

    cryo_id: str
    name: str
    manufacturer: str
    model: str
    location: str
    status: str
    commissioned_at: datetime | None
    decommissioned_at: datetime | None
    note: NoteModel = Field(default_factory=NoteModel)


class ListCryostatsResponse(BaseModel):
    cryostats: list[CryostatResponse]
