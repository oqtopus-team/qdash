"""Document model for task result comments."""

from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class TaskResultCommentDocument(Document):
    """Document for storing comments on task results.

    Each document represents a single comment on a task result,
    enabling multi-comment discussion threads per task.

    Attributes
    ----------
        project_id (str): The project ID for multi-tenancy.
        task_id (str): The task ID this comment is associated with.
        username (str): The username of the comment author.
        content (str): The comment text content.
        system_info (SystemInfoModel): Created/updated timestamps.

    """

    project_id: str = Field(..., description="Owning project identifier")
    task_id: str = Field(..., description="The task ID this comment belongs to")
    username: str = Field(..., description="The username of the comment author")
    content: str = Field(..., description="The comment text content")
    parent_id: str | None = Field(
        default=None, description="Parent comment ID for replies. None for root comments."
    )
    is_closed: bool = Field(
        default=False,
        description="Whether this thread is closed. Only meaningful for root comments.",
    )
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "task_result_comment"
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
