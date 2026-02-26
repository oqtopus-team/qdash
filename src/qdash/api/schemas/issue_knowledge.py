"""Schema definitions for issue-derived knowledge cases."""

from datetime import datetime

from pydantic import BaseModel, Field


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

    reviewed_by: str | None = Field(default=None, description="Reviewer username")
    created_at: datetime = Field(..., description="When the draft was created")
    updated_at: datetime = Field(..., description="When the draft was last updated")


class IssueKnowledgeUpdate(BaseModel):
    """Request schema for editing a knowledge draft."""

    title: str | None = Field(default=None, max_length=200, description="Updated title")
    severity: str | None = Field(default=None, description="Updated severity")
    symptom: str | None = Field(default=None, max_length=5000, description="Updated symptom")
    root_cause: str | None = Field(default=None, max_length=5000, description="Updated root cause")
    resolution: str | None = Field(default=None, max_length=5000, description="Updated resolution")
    lesson_learned: list[str] | None = Field(default=None, description="Updated lessons")


class ListIssueKnowledgeResponse(BaseModel):
    """Paginated list of knowledge cases."""

    items: list[IssueKnowledgeResponse]
    total: int
    skip: int
    limit: int
