"""Current-state storage for dashboard target summary notes.

Target notes are scoped by either a cool-down, a manual time range, or a global
legacy scope. This stores pinned summaries independently from deprecated
per-metric dashboard notes.
"""

from datetime import datetime
from typing import ClassVar, Literal

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.datamodel.note import NoteCommentModel, NoteModel
from qdash.datamodel.system_info import SystemInfoModel

TargetNoteTargetType = Literal["qubit", "coupling"]
TargetNoteScopeType = Literal["cooldown", "time_range", "global"]
TargetNoteScopeSource = Literal[
    "explicit_cooldown",
    "current_cooldown",
    "inferred_from_range",
    "manual_time_range",
    "legacy_global",
]


class TargetNoteDocument(Document):
    """Current pinned summary for one target in one operational scope."""

    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field(..., description="Chip identifier")
    target_type: str = Field(..., description="qubit | coupling")
    target_id: str = Field(..., description="Qubit id or coupling id")
    note: NoteModel = Field(default_factory=NoteModel, description="Current note value")
    comments: list[NoteCommentModel] = Field(
        default_factory=list, description="User-authored comments on this target summary"
    )

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

        name = "target_note"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("target_type", ASCENDING),
                    ("target_id", ASCENDING),
                    ("scope_key", ASCENDING),
                ],
                unique=True,
                name="target_note_unique_scope_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("scope_key", ASCENDING),
                    ("target_type", ASCENDING),
                    ("target_id", ASCENDING),
                ],
                name="target_note_summary_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("scope_started_at", DESCENDING),
                    ("scope_ended_at", DESCENDING),
                ],
                name="target_note_time_scope_idx",
            ),
        ]

    model_config = ConfigDict(from_attributes=True)
