"""Current-state storage for dashboard metric notes.

Metric notes are scoped by either a cool-down, a manual time range, or a global
legacy scope. The scope stores both a stable key and time bounds so notes remain
usable for teams that add cool-down documents after notes were written.
"""

from datetime import datetime
from typing import ClassVar, Literal

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.datamodel.note import NoteModel
from qdash.datamodel.system_info import SystemInfoModel

MetricNoteTargetType = Literal["qubit", "coupling"]
MetricNoteScopeType = Literal["cooldown", "time_range", "global"]
MetricNoteScopeSource = Literal[
    "explicit_cooldown",
    "current_cooldown",
    "inferred_from_range",
    "manual_time_range",
    "legacy_global",
]


class MetricNoteDocument(Document):
    """Current note for one target metric in one operational scope."""

    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field(..., description="Chip identifier")
    target_type: str = Field(..., description="qubit | coupling")
    target_id: str = Field(..., description="Qubit id or coupling id")
    metric_key: str = Field(..., description="Metric key")
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

        name = "metric_note"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("target_type", ASCENDING),
                    ("target_id", ASCENDING),
                    ("metric_key", ASCENDING),
                    ("scope_key", ASCENDING),
                ],
                unique=True,
                name="metric_note_unique_scope_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("scope_key", ASCENDING),
                    ("target_type", ASCENDING),
                    ("target_id", ASCENDING),
                ],
                name="metric_note_summary_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("scope_started_at", DESCENDING),
                    ("scope_ended_at", DESCENDING),
                ],
                name="metric_note_time_scope_idx",
            ),
        ]

    model_config = ConfigDict(from_attributes=True)
