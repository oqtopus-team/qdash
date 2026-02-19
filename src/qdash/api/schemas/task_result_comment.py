"""Schema definitions for task result comments."""

from datetime import datetime

from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    """Request schema for creating a comment."""

    content: str = Field(..., min_length=1, max_length=5000, description="Comment text content")
    parent_id: str | None = Field(
        default=None, description="Parent comment ID for replies. None for root comments."
    )


class CommentResponse(BaseModel):
    """Response schema for a single comment."""

    id: str = Field(..., description="Comment document ID")
    task_id: str = Field(..., description="Associated task ID")
    username: str = Field(..., description="Comment author username")
    content: str = Field(..., description="Comment text content")
    created_at: datetime = Field(..., description="When the comment was created")
    parent_id: str | None = Field(default=None, description="Parent comment ID for replies")
    reply_count: int = Field(default=0, description="Number of replies to this comment")
    is_closed: bool = Field(default=False, description="Whether this thread is closed")


class ListCommentsResponse(BaseModel):
    """Paginated list of comments."""

    comments: list[CommentResponse]
    total: int
    skip: int
    limit: int
