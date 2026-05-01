"""Append-only audit log for every note edit.

The ``NoteEventDocument`` collection is a write-through log: every upsert or
delete of a note (qubit, coupling, qubit/coupling-metric, or task-result) writes
one row here. The collection is append-only — never updated in place.

This separates two concerns:
- Inline notes on the parent document = "current state" (fast read with parent)
- NoteEvent log = "history / search / knowledge feed" (audited, indexed, mineable)

Use cases:
- Per-target / per-chip annotation timeline
- Cross-chip text search ("which qubits have ever been called 'unstable'?")
- Source for LLM context, knowledge views, etc.
"""

from datetime import datetime
from typing import ClassVar, Literal

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.common.datetime_utils import now

NoteScope = Literal[
    "qubit",
    "qubit_metric",
    "coupling",
    "coupling_metric",
    "task_result",
]
NoteAction = Literal["upsert", "delete"]


class NoteEventDocument(Document):
    """One audit-log row per note edit."""

    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field(..., description="Chip identifier (denormalized for filtering)")
    scope: str = Field(
        ..., description="One of: qubit | qubit_metric | coupling | coupling_metric | task_result"
    )
    target_id: str = Field(
        ...,
        description=(
            "qid for qubit/qubit_metric, coupling_id for coupling/coupling_metric, "
            "task_id for task_result."
        ),
    )
    metric_key: str = Field(default="", description="Metric key for *_metric scopes; '' otherwise")
    action: str = Field(..., description="upsert | delete")
    actor: str = Field(..., description="Username who performed the action")
    content: str = Field(default="", description="Note content at the time of the action")
    # Free-form context, e.g. {"qid": "5", "task_name": "T1"} — populated where useful
    extra: dict[str, str] = Field(default_factory=dict, description="Arbitrary context tags")
    created_at: datetime = Field(default_factory=now, description="When this event was recorded")

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Settings for the document."""

        name = "note_event"
        indexes: ClassVar = [
            # chip-scoped chronological feed
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="chip_chrono_idx",
            ),
            # per-target timeline (e.g. "all events on Q5")
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("scope", ASCENDING),
                    ("target_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="target_chrono_idx",
            ),
            # text index on content for cross-chip knowledge search
            IndexModel(
                [("content", "text")],
                name="content_text_idx",
                default_language="english",
            ),
        ]
