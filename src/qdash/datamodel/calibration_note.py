"""Data model for calibration notes.

This module defines the domain model for calibration notes,
separate from the database document representation.
"""

from typing import Any

from pydantic import BaseModel, Field
from qdash.datamodel.system_info import SystemInfoModel


class CalibrationNoteModel(BaseModel):
    """Domain model for a calibration note.

    This is a pure domain model without any database-specific logic.
    Use CalibrationNoteRepository for persistence operations.

    Attributes
    ----------
        project_id: The project ID for multi-tenancy.
        username: The username of the user who created the note.
        chip_id: The chip ID associated with this note.
        execution_id: The execution ID associated with this note.
        task_id: The task ID associated with this note.
        note: The calibration note data (arbitrary dict).
        timestamp: The time when the note was last updated (ISO 8601).
        system_info: The system information (created_at, updated_at).

    Example
    -------
        >>> note = CalibrationNoteModel(
        ...     project_id="project-1",
        ...     username="alice",
        ...     chip_id="64Qv3",
        ...     execution_id="20240101-001",
        ...     task_id="master",
        ...     note={"qubit_0": {"frequency": 5.0}},
        ... )

    """

    project_id: str = Field(..., description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the note")
    chip_id: str = Field(..., description="The chip ID associated with this note")
    execution_id: str = Field(..., description="The execution ID associated with this note")
    task_id: str = Field(..., description="The task ID associated with this note")
    note: dict[str, Any] = Field(default_factory=dict, description="The calibration note data")
    timestamp: str | None = Field(
        default=None,
        description="The time when the note was last updated (ISO 8601)",
    )
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel,
        description="The system information",
    )
