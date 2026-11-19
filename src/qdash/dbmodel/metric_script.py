"""Metric script document."""

from typing import ClassVar
from uuid import uuid4

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.datamodel.metric_script import (
    MetricInfo,
    MetricScriptRevision,
    MetricScriptStatus,
    MetricScriptVisibility,
    ScriptDiagnostic,
)
from qdash.datamodel.system_info import SystemInfoModel


def _new_script_id() -> str:
    return f"ms_{uuid4().hex[:12]}"


class MetricScriptDocument(Document):
    """A user-authored Python metric script with its revision history.

    ``source`` is the latest saved text. ``active_*`` describe the last revision that
    validated ("last good"); a failed save leaves them unchanged.
    """

    project_id: str = Field(..., description="Owning project identifier")
    script_id: str = Field(default_factory=_new_script_id, description="Project-unique ID")
    user_id: str | None = Field(default=None, description="Owner user ID")
    username: str = Field(..., description="Owner username snapshot")
    name: str = Field(..., description="Display name")
    description: str = Field(default="", description="Free-form description")
    visibility: MetricScriptVisibility = Field(
        default="private",
        description="'private' (owner only) or 'project' (all project members)",
    )
    source: str = Field(..., description="Latest saved source text")
    revision: int = Field(default=1, description="Latest revision; increments on every save")
    status: MetricScriptStatus = Field(..., description="Validation status of the latest save")
    diagnostics: list[ScriptDiagnostic] = Field(
        default_factory=list, description="Problems found in the latest save"
    )
    active_revision: int | None = Field(
        default=None, description="Last revision that validated; None if none did"
    )
    active_source: str | None = Field(default=None, description="Source of the active revision")
    metrics: list[MetricInfo] = Field(
        default_factory=list, description="Catalog of the active revision"
    )
    revisions: list[MetricScriptRevision] = Field(
        default_factory=list, description="Saved revisions, oldest first"
    )
    template_id: str | None = Field(
        default=None, description="Template the script was created from, if any"
    )
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="Created/updated timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "metric_script"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("script_id", ASCENDING)],
                unique=True,
                name="project_script_unique",
            ),
            IndexModel([("project_id", ASCENDING), ("visibility", ASCENDING)]),
            IndexModel([("project_id", ASCENDING), ("user_id", ASCENDING)]),
            IndexModel([("project_id", ASCENDING), ("template_id", ASCENDING)]),
        ]

    model_config = ConfigDict(from_attributes=True)

    def find_revision(self, revision: int) -> MetricScriptRevision | None:
        """Return a stored revision by number."""
        return next((item for item in self.revisions if item.revision == revision), None)
