"""Document model for issue-derived knowledge cases."""

from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class IssueKnowledgeDocument(Document):
    """A knowledge case extracted from a closed issue thread.

    Lifecycle: draft -> approved | rejected
    Approved cases are exported to docs/task-knowledge/<task>/cases/*.md
    and included in the task-knowledge.json consumed by the copilot.

    Attributes
    ----------
        project_id (str): The project ID for multi-tenancy.
        issue_id (str): The root issue this knowledge was derived from.
        task_id (str): The task result ID the issue was associated with.
        task_name (str): The calibration task class name (e.g. CheckT1).
        status (str): Lifecycle status: draft, approved, rejected.
        title (str): Short descriptive title of the case.
        date (str): Date of the incident (YYYY-MM-DD).
        severity (str): Severity: critical, warning, info.
        chip_id (str): Chip identifier.
        qid (str): Qubit identifier.
        resolution_status (str): Case outcome: resolved, open, workaround.
        symptom (str): Observed symptom.
        root_cause (str): Identified root cause.
        resolution (str): How the issue was resolved.
        lesson_learned (list[str]): Key takeaways.
        reviewed_by (str | None): Username of the reviewer.
        system_info (SystemInfoModel): Created/updated timestamps.

    """

    project_id: str = Field(..., description="Owning project identifier")
    issue_id: str = Field(..., description="Root issue ID this knowledge was derived from")
    task_id: str = Field(..., description="Task result ID the issue was associated with")
    task_name: str = Field(..., description="Calibration task class name (e.g. CheckT1)")
    status: str = Field(default="draft", description="Lifecycle status: draft, approved, rejected")

    # Case content
    title: str = Field(..., description="Short descriptive title")
    date: str = Field(default="", description="Date of the incident (YYYY-MM-DD)")
    severity: str = Field(default="warning", description="Severity: critical, warning, info")
    chip_id: str = Field(default="", description="Chip identifier")
    qid: str = Field(default="", description="Qubit identifier")
    resolution_status: str = Field(
        default="resolved", description="Case outcome: resolved, open, workaround"
    )
    symptom: str = Field(default="", description="Observed symptom")
    root_cause: str = Field(default="", description="Identified root cause")
    resolution: str = Field(default="", description="How the issue was resolved")
    lesson_learned: list[str] = Field(default_factory=list, description="Key takeaways")

    # Images
    figure_paths: list[str] = Field(
        default_factory=list, description="Task result figure paths (from calibration output)"
    )
    thread_image_urls: list[str] = Field(
        default_factory=list, description="Image URLs from the issue thread discussion"
    )

    reviewed_by: str | None = Field(default=None, description="Username of the reviewer")
    pr_url: str | None = Field(default=None, description="GitHub PR URL created on approve")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "issue_knowledge"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("task_name", ASCENDING),
                    ("status", ASCENDING),
                ],
                name="project_task_status_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("issue_id", ASCENDING),
                ],
                name="project_issue_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("system_info.created_at", DESCENDING),
                ],
                name="project_created_idx",
            ),
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )
