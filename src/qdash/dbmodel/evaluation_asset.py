"""Content-addressed image snapshots used by calibration evaluations."""

from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.common.utils.datetime import now


class EvaluationAssetDocument(Document):
    """One immutable image, deduplicated per project by its SHA-256."""

    project_id: str
    sha256: str
    mime_type: str
    bytes: int
    base64_data: str = Field(..., description="Exact image bytes encoded as base64")
    created_at: datetime = Field(default_factory=now)

    model_config = ConfigDict(from_attributes=True)

    class Settings:
        """Mongo metadata."""

        name = "evaluation_asset"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("sha256", ASCENDING)],
                unique=True,
                name="evaluation_asset_project_sha_unique_idx",
            )
        ]
