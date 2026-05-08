"""Cool-down cycle document.

A ``CooldownDocument`` represents one cool-down / warm-up cycle of a cryostat.
Multiple chips may be loaded into the same cooldown.
"""

from datetime import datetime
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.datamodel.note import NoteModel
from qdash.datamodel.system_info import SystemInfoModel


class CooldownDocument(Document):
    """One cool-down cycle of one cryostat."""

    project_id: str = Field(..., description="Owning project identifier")
    cooldown_id: str = Field(..., description="Project-unique identifier (e.g. '2026-001')")
    cryo_id: str = Field(..., description="Owning cryostat identifier")
    description: str = Field(default="", description="Free-form description")
    started_at: datetime = Field(..., description="When the cool-down started")
    ended_at: datetime | None = Field(
        default=None,
        description="When the cool-down ended (None = ongoing)",
    )
    chip_ids: list[str] = Field(
        default_factory=list,
        description="Chips loaded into this cool-down (in the cryostat at the same time)",
    )
    note: NoteModel = Field(default_factory=NoteModel, description="Free-form note")
    wiring_info: str = Field(
        default="",
        description=(
            "Markdown export of the wiring document — kept in sync with "
            "wiring_blocks for fallback rendering, search, and export."
        ),
    )
    wiring_blocks: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "BlockNote document (list of Block JSON objects). Authoritative "
            "source for the rich editor; wiring_info is derived from this. "
            "Images are embedded inline as data URLs in image blocks."
        ),
    )
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="Created/updated timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "cooldown"
        indexes: ClassVar = [
            # Unique cooldown_id within a project
            IndexModel(
                [("project_id", ASCENDING), ("cooldown_id", ASCENDING)],
                unique=True,
                name="project_cooldown_unique",
            ),
            # List by cryostat, newest first
            IndexModel(
                [("project_id", ASCENDING), ("cryo_id", ASCENDING), ("started_at", DESCENDING)],
                name="project_cryo_started_idx",
            ),
            # Find cool-downs containing a chip
            IndexModel(
                [("project_id", ASCENDING), ("chip_ids", ASCENDING), ("started_at", DESCENDING)],
                name="project_chip_idx",
            ),
            # Time-range filter (e.g. for backfilling cooldown_id on history rows)
            IndexModel(
                [("project_id", ASCENDING), ("started_at", DESCENDING)],
                name="project_started_idx",
            ),
        ]

    model_config = ConfigDict(from_attributes=True)
