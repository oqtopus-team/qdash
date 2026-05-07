"""Document model for project forum discussions."""

from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class ForumCategoryDocument(Document):
    """Project-scoped forum category."""

    project_id: str = Field(..., description="Owning project identifier")
    key: str = Field(..., description="Stable category key")
    name: str = Field(..., description="Display name")
    description: str = Field(default="", description="Short category description")
    color: str = Field(default="neutral", description="Display color token")
    icon: str = Field(default="message-square", description="Display icon token")
    sort_order: int = Field(default=100, description="Display order")
    is_archived: bool = Field(default=False, description="Whether this category is hidden")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "forum_category"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("key", ASCENDING)],
                unique=True,
                name="project_key_unique_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("is_archived", ASCENDING),
                    ("sort_order", ASCENDING),
                    ("system_info.created_at", DESCENDING),
                ],
                name="project_archived_order_idx",
            ),
        ]

    model_config = ConfigDict(from_attributes=True)


class ForumPostDocument(Document):
    """Project-scoped forum thread or reply."""

    project_id: str = Field(..., description="Owning project identifier")
    category: str = Field(..., description="Forum category for root threads")
    username: str = Field(..., description="The username of the post author")
    title: str | None = Field(default=None, description="Thread title. Only for root posts.")
    content: str = Field(..., description="Markdown post content")
    parent_id: str | None = Field(
        default=None, description="Parent forum post ID for replies. None for root threads."
    )
    is_closed: bool = Field(
        default=False,
        description="Whether this thread is closed. Only meaningful for root threads.",
    )
    is_deleted: bool = Field(default=False, description="Whether this post is archived/deleted")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="System timestamps"
    )

    class Settings:
        """Settings for the document."""

        name = "forum_post"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("parent_id", ASCENDING),
                    ("is_deleted", ASCENDING),
                    ("system_info.created_at", ASCENDING),
                ],
                name="project_parent_deleted_created_idx",
            ),
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("category", ASCENDING),
                    ("is_deleted", ASCENDING),
                    ("system_info.created_at", ASCENDING),
                ],
                name="project_category_deleted_created_idx",
            ),
        ]

    model_config = ConfigDict(from_attributes=True)
