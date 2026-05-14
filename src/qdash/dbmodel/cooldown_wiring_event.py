"""Append-only history of wiring changes within a single cool-down.

Autosave to ``CooldownDocument.wiring_blocks`` keeps the *current* wiring up to
date but produces no history. When a user makes a real wiring change during a
cool-down (e.g. swaps a MUX line, adds an attenuator) they record a
**checkpoint** — one row in this collection — capturing a comment, the actor,
and a snapshot of the wiring markdown at that moment.

Modelled on ``NoteEventDocument`` but kept in its own collection because:
- target is a cool-down (not a chip-level entity)
- we store a snapshot string, not just text content
- we want a dedicated index keyed on ``cooldown_id``
"""

from datetime import datetime
from typing import ClassVar, Literal

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.utils.datetime import now

WiringEventAction = Literal["checkpoint"]


class CooldownWiringEventDocument(Document):
    """One audit-log row per wiring checkpoint."""

    project_id: str = Field(..., description="Owning project identifier")
    cooldown_id: str = Field(..., description="Cool-down this event belongs to")
    actor_user_id: str | None = Field(default=None, description="User ID who recorded checkpoint")
    actor: str = Field(..., description="Username snapshot who recorded the checkpoint")
    action: str = Field(default="checkpoint", description="checkpoint")
    comment: str = Field(..., description="Why the wiring changed (required at checkpoint time)")
    wiring_info_snapshot: str = Field(
        default="",
        description="Markdown snapshot of wiring_info at checkpoint time (used for diff/preview)",
    )
    block_count: int = Field(default=0, description="Number of BlockNote blocks at checkpoint time")
    image_count: int = Field(
        default=0, description="Number of image blocks at checkpoint time (rough size hint)"
    )
    extra: dict[str, str] = Field(default_factory=dict, description="Free-form context tags")
    created_at: datetime = Field(default_factory=now, description="When the checkpoint was taken")

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Settings for the document."""

        name = "cooldown_wiring_event"
        indexes: ClassVar = [
            # Per-cooldown chronological feed (primary read path)
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("cooldown_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="cooldown_chrono_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("actor_user_id", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="actor_user_id_chrono_idx",
            ),
            # Cross-cooldown text search over comments + snapshots
            IndexModel(
                [("comment", "text"), ("wiring_info_snapshot", "text")],
                name="wiring_text_idx",
                default_language="english",
            ),
        ]
