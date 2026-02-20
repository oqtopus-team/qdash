"""Schema definitions for issues."""

from datetime import datetime

from pydantic import BaseModel, Field


class IssueCreate(BaseModel):
    """Request schema for creating an issue."""

    title: str | None = Field(
        default=None,
        max_length=200,
        description="Issue title. Required for root issues, None for replies.",
    )
    content: str = Field(..., min_length=1, max_length=5000, description="Issue text content")
    parent_id: str | None = Field(
        default=None, description="Parent issue ID for replies. None for root issues."
    )


class IssueResponse(BaseModel):
    """Response schema for a single issue."""

    id: str = Field(..., description="Issue document ID")
    task_id: str = Field(..., description="Associated task ID")
    username: str = Field(..., description="Issue author username")
    title: str | None = Field(default=None, description="Issue title")
    content: str = Field(..., description="Issue text content")
    created_at: datetime = Field(..., description="When the issue was created")
    parent_id: str | None = Field(default=None, description="Parent issue ID for replies")
    reply_count: int = Field(default=0, description="Number of replies to this issue")
    is_closed: bool = Field(default=False, description="Whether this thread is closed")


class ListIssuesResponse(BaseModel):
    """Paginated list of issues."""

    issues: list[IssueResponse]
    total: int
    skip: int
    limit: int
