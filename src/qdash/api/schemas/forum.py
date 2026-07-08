"""Schema definitions for forum discussions."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

FORUM_CATEGORY_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
FORUM_CATEGORY_COLOR_PATTERN = (
    r"^(neutral|primary|secondary|accent|info|success|warning|error|ghost)$"
)
FORUM_CATEGORY_ICON_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"
FORUM_TARGET_TYPE_PATTERN = r"^(qubit|coupling)$"


class ForumCategoryCreate(BaseModel):
    """Request schema for creating a forum category."""

    key: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=FORUM_CATEGORY_PATTERN,
        description="Stable category key. Generated from name when omitted.",
    )
    name: str = Field(..., min_length=1, max_length=80, description="Display name")
    description: str = Field(default="", max_length=200, description="Short description")
    color: str = Field(
        default="neutral",
        pattern=FORUM_CATEGORY_COLOR_PATTERN,
        description="Display color token",
    )
    icon: str = Field(
        default="message-square",
        max_length=64,
        pattern=FORUM_CATEGORY_ICON_PATTERN,
        description="Display icon token",
    )
    sort_order: int | None = Field(default=None, ge=0, le=10000, description="Display order")


class ForumCategoryUpdate(BaseModel):
    """Request schema for updating a forum category."""

    name: str | None = Field(default=None, min_length=1, max_length=80, description="Display name")
    description: str | None = Field(default=None, max_length=200, description="Short description")
    color: str | None = Field(
        default=None,
        pattern=FORUM_CATEGORY_COLOR_PATTERN,
        description="Display color token",
    )
    icon: str | None = Field(
        default=None,
        max_length=64,
        pattern=FORUM_CATEGORY_ICON_PATTERN,
        description="Display icon token",
    )
    sort_order: int | None = Field(default=None, ge=0, le=10000, description="Display order")
    is_archived: bool | None = Field(default=None, description="Whether this category is hidden")


class ForumCategoryResponse(BaseModel):
    """Response schema for a forum category."""

    id: str = Field(..., description="Forum category document ID")
    project_id: str = Field(..., description="Owning project identifier")
    key: str = Field(..., description="Stable category key")
    name: str = Field(..., description="Display name")
    description: str = Field(default="", description="Short category description")
    color: str = Field(default="neutral", description="Display color token")
    icon: str = Field(default="message-square", description="Display icon token")
    sort_order: int = Field(default=100, description="Display order")
    is_archived: bool = Field(default=False, description="Whether this category is hidden")


class ListForumCategoriesResponse(BaseModel):
    """List of forum categories."""

    categories: list[ForumCategoryResponse]


class ForumPostCreate(BaseModel):
    """Request schema for creating a forum thread or reply."""

    category: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=FORUM_CATEGORY_PATTERN,
        description="Forum category key",
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description="Thread title. Required for root threads, None for replies.",
    )
    content: str = Field(..., min_length=1, max_length=8000, description="Markdown content")
    content_blocks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="BlockNote document JSON. Source of truth for rich content; content is derived.",
    )
    parent_id: str | None = Field(
        default=None, description="Parent forum post ID for replies. None for root threads."
    )
    labels: list[str] = Field(
        default_factory=list,
        max_length=1,
        description="Operator label for root threads",
    )
    assignee_username: str | None = Field(
        default=None, max_length=64, description="Assigned project member username"
    )
    chip_id: str | None = Field(default=None, max_length=128, description="Linked chip ID")
    target_type: str | None = Field(
        default=None,
        pattern=FORUM_TARGET_TYPE_PATTERN,
        description="Linked target type",
    )
    target_id: str | None = Field(default=None, max_length=128, description="Linked target ID")
    cooldown_id: str | None = Field(default=None, max_length=128, description="Linked cool-down ID")


class ForumPostUpdate(BaseModel):
    """Request schema for updating a forum post."""

    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=FORUM_CATEGORY_PATTERN,
        description="Updated forum category key for root threads",
    )
    title: str | None = Field(
        default=None, max_length=200, description="Updated title for root threads"
    )
    content: str = Field(..., min_length=1, max_length=8000, description="Updated content")
    content_blocks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="BlockNote document JSON. Source of truth for rich content; content is derived.",
    )
    labels: list[str] | None = Field(
        default=None,
        max_length=1,
        description="Updated operator label for root threads",
    )
    assignee_username: str | None = Field(
        default=None, max_length=64, description="Updated assigned project member username"
    )
    chip_id: str | None = Field(default=None, max_length=128, description="Updated linked chip ID")
    target_type: str | None = Field(
        default=None,
        pattern=FORUM_TARGET_TYPE_PATTERN,
        description="Updated linked target type",
    )
    target_id: str | None = Field(
        default=None, max_length=128, description="Updated linked target ID"
    )
    cooldown_id: str | None = Field(
        default=None, max_length=128, description="Updated linked cool-down ID"
    )


class ForumAiReplyRequest(BaseModel):
    """Request schema for AI reply in a forum thread."""

    user_message: str = Field(..., min_length=1, max_length=8000, description="User message to AI")


class ForumPostResponse(BaseModel):
    """Response schema for a forum post."""

    id: str = Field(..., description="Forum post document ID")
    project_id: str = Field(..., description="Owning project identifier")
    number: int | None = Field(
        default=None,
        ge=1,
        description="Project-scoped forum thread number. Replies share the root thread number.",
    )
    category: str = Field(..., description="Forum category key")
    user_id: str | None = Field(default=None, description="Post author user ID")
    username: str = Field(..., description="Post author username")
    avatar_key: str | None = Field(default=None, description="Post author avatar preset key")
    title: str | None = Field(default=None, description="Thread title")
    content: str = Field(..., description="Markdown content")
    content_blocks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="BlockNote document JSON. Source of truth for rich content; content is derived.",
    )
    parent_id: str | None = Field(default=None, description="Parent forum post ID")
    labels: list[str] = Field(default_factory=list, description="Operator label for root threads")
    assignee_username: str | None = Field(
        default=None, description="Assigned project member username"
    )
    chip_id: str | None = Field(default=None, description="Linked chip ID")
    target_type: str | None = Field(default=None, description="Linked target type")
    target_id: str | None = Field(default=None, description="Linked target ID")
    cooldown_id: str | None = Field(default=None, description="Linked cool-down ID")
    reply_count: int = Field(default=0, description="Number of replies to this thread")
    is_closed: bool = Field(default=False, description="Whether this thread is closed")
    is_deleted: bool = Field(default=False, description="Whether this post is archived/deleted")
    is_ai_reply: bool = Field(default=False, description="Whether this reply was generated by AI")
    created_at: datetime = Field(..., description="When the post was created")
    updated_at: datetime = Field(..., description="When the post was last updated")


class ListForumPostsResponse(BaseModel):
    """Paginated list of forum posts."""

    posts: list[ForumPostResponse]
    total: int
    skip: int
    limit: int
