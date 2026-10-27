"""Schemas for the shared Qubex box catalog (``config/box.yaml``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from qdash.api.schemas.chip import ChipPublishStatus  # noqa: TC001 - pydantic field type


class ConfigBox(BaseModel):
    """One control box as ``box.yaml`` describes it."""

    box_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", max_length=64)
    name: str = Field(max_length=200)
    type: str = Field(description="A qubex BoxType value, e.g. quel1se-riken8 or quel3")
    address: str | None = Field(default=None, description="Required for QuBE and QuEL-1 boxes")
    adapter: str | None = Field(default=None, description="Required for QuBE and QuEL-1 boxes")
    options: list[str] | None = Field(default=None, description="Backend-specific box options")
    extra: dict[str, Any] = Field(
        default_factory=dict, description="Other keys of the entry, kept as they are"
    )


class ListConfigBoxesResponse(BaseModel):
    """The box catalog and the types a box may have."""

    layout: str
    editable: bool = Field(description="Whether boxes can be registered (shared layout)")
    boxes: list[ConfigBox] = Field(default_factory=list)
    box_types: list[str] = Field(default_factory=list)
    message: str | None = None


class UpsertConfigBoxResponse(BaseModel):
    """Result of registering or updating a box."""

    box: ConfigBox
    created: bool
    publish: ChipPublishStatus
