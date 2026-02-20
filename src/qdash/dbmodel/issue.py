"""Document model for issues."""

from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class IssueDocument(Document):
    """Document for storing issues on task results.

    Each document represents a single issue or reply on a task result,
    enabling multi-issue discussion threads per task.

    Attributes
    ----------
        project_id (str): The project ID for multi-tenancy.
        task_id (str): The task ID this issue is associated with.
        username (str): The username of the issue author.
        title (str | None): Issue title. Only for root issues.
        content (str): The issue text content.
        parent_id (str | None): Parent issue ID for replies. None for root issues.
        is_closed (bool): Whether this thread is closed.
        system_info (SystemInfoModel): Created/updated timestamps.

    """

    project_id: str = Field(..., description="Owning project identifier")
    task_id: str = Field(..., description="The task ID this issue belongs to")
    username: str = Field(..., description="The username of the issue author")
    title: str | None = Field(default=None, description="Issue title. Only for root issues.")
    content: str = Field(..., description="The issue text content")
    parent_id: str | None = Field(
        default=None, description="Parent issue ID for replies. None for root issues."
    )
    is_closed: bool = Field(
        default=False,
        description="Whether this thread is closed. Only meaningful for root issues.",
    )
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "issue"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("task_id", ASCENDING),
                    ("system_info.created_at", ASCENDING),
                ],
                name="project_task_created_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("parent_id", ASCENDING),
                ],
                name="project_parent_idx",
            ),
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )
