"""Schema definitions for issue-derived knowledge cases."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class IssueKnowledgeResponse(BaseModel):
    """Response schema for a knowledge case."""

    id: str = Field(..., description="Document ID")
    issue_id: str = Field(..., description="Source issue ID")
    task_id: str = Field(..., description="Associated task result ID")
    task_name: str = Field(..., description="Calibration task class name")
    status: str = Field(..., description="Lifecycle status: draft, approved, rejected")

    title: str = Field(..., description="Short descriptive title")
    date: str = Field(default="", description="Date of the incident")
    severity: str = Field(default="warning", description="Severity level")
    chip_id: str = Field(default="", description="Chip identifier")
    qid: str = Field(default="", description="Qubit identifier")
    resolution_status: str = Field(default="resolved", description="Case outcome")
    symptom: str = Field(default="", description="Observed symptom")
    root_cause: str = Field(default="", description="Identified root cause")
    resolution: str = Field(default="", description="How the issue was resolved")
    lesson_learned: list[str] = Field(default_factory=list, description="Key takeaways")

    figure_paths: list[str] = Field(default_factory=list, description="Task result figure paths")
    thread_image_urls: list[str] = Field(
        default_factory=list, description="Image URLs from issue thread"
    )

    reviewed_by: str | None = Field(default=None, description="Reviewer username")
    pr_url: str | None = Field(default=None, description="GitHub PR URL (set on approve)")
    created_at: datetime = Field(..., description="When the draft was created")
    updated_at: datetime = Field(..., description="When the draft was last updated")


_VALID_SEVERITIES = {"critical", "warning", "info"}


class IssueKnowledgeUpdate(BaseModel):
    """Request schema for editing a knowledge draft."""

    title: str | None = Field(default=None, max_length=200, description="Updated title")
    severity: Literal["critical", "warning", "info"] | None = Field(
        default=None, description="Updated severity"
    )
    symptom: str | None = Field(default=None, max_length=5000, description="Updated symptom")
    root_cause: str | None = Field(default=None, max_length=5000, description="Updated root cause")
    resolution: str | None = Field(default=None, max_length=5000, description="Updated resolution")
    lesson_learned: list[str] | None = Field(
        default=None, max_length=50, description="Updated lessons"
    )

    @field_validator("lesson_learned")
    @classmethod
    def validate_lessons(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for lesson in v:
                if len(lesson) > 2000:
                    msg = "Each lesson must be at most 2000 characters"
                    raise ValueError(msg)
        return v


class ListIssueKnowledgeResponse(BaseModel):
    """Paginated list of knowledge cases."""

    items: list[IssueKnowledgeResponse]
    total: int
    skip: int
    limit: int
