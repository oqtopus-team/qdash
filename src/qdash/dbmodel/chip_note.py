"""Current-state storage for dashboard chip notes.

Chip notes are scoped by cool-down, manual time range, or the legacy global
chip note field. Scoped notes let dashboard context follow the selected
cool-down without overwriting chip-wide metadata.
"""

from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.datamodel.note import NoteModel
from qdash.datamodel.system_info import SystemInfoModel


class ChipNoteDocument(Document):
    """Current pinned summary for one chip in one operational scope."""

    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field(..., description="Chip identifier")
    note: NoteModel = Field(default_factory=NoteModel, description="Current note value")

    scope_type: str = Field(..., description="cooldown | time_range | global")
    scope_key: str = Field(..., description="Stable key unique within the scope")
    cooldown_id: str | None = Field(default=None, description="Cooldown identifier if known")
    scope_started_at: datetime | None = Field(default=None, description="Scope start time in UTC")
    scope_ended_at: datetime | None = Field(default=None, description="Scope end time in UTC")
    scope_source: str = Field(..., description="How the scope was resolved")

    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="Created/updated timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "chip_note"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("scope_key", ASCENDING),
                ],
                unique=True,
                name="chip_note_unique_scope_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("scope_started_at", DESCENDING),
                    ("scope_ended_at", DESCENDING),
                ],
                name="chip_note_time_scope_idx",
            ),
        ]

    model_config = ConfigDict(from_attributes=True)
