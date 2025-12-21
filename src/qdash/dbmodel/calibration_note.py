from datetime import datetime
from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.common.datetime_utils import now
from qdash.datamodel.system_info import SystemInfoModel


class CalibrationNoteDocument(Document):
    """Document for storing calibration notes.

    Attributes
    ----------
        project_id (str): The project ID for multi-tenancy.
        username (str): The username of the user who created the note.
        chip_id (str): The chip ID associated with this note.
        execution_id (str): The execution ID associated with this note.
        task_id (str): The task ID associated with this note.
        note (dict): The calibration note data.
        timestamp (datetime): The time when the note was last updated.
        system_info (SystemInfoModel): The system information.

    """

    project_id: str = Field(..., description="Owning project identifier")
    username: str = Field(..., description="The username of the user who created the note")
    chip_id: str = Field(..., description="The chip ID associated with this note")
    execution_id: str = Field(..., description="The execution ID associated with this note")
    task_id: str = Field(..., description="The task ID associated with this note")
    note: dict[str, Any] = Field(..., description="The calibration note data")
    timestamp: datetime = Field(
        default_factory=now,
        description="The time when the note was last updated",
    )
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="The system information"
    )

    class Settings:
        """Settings for the document."""

        name = "calibration_note"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("execution_id", ASCENDING),
                    ("task_id", ASCENDING),
                    ("username", ASCENDING),
                    ("chip_id", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("timestamp", ASCENDING)],
                name="project_chip_timestamp_idx",
            ),
        ]

    @classmethod
    def upsert_note(
        cls,
        username: str,
        chip_id: str,
        execution_id: str,
        task_id: str,
        note: dict[str, Any],
        project_id: str,
    ) -> "CalibrationNoteDocument":
        """Upsert a calibration note.

        Args:
        ----
            username (str): The username of the user who created the note.
            chip_id (str): The chip ID associated with this note.
            execution_id (str): The execution ID associated with this note.
            task_id (str): The task ID associated with this note.
            note (dict): The calibration note data.
            project_id (str): The project ID for multi-tenancy.

        Returns:
        -------
            CalibrationNoteDocument: The upserted document.

        """
        doc = cls.find_one(
            {
                "project_id": project_id,
                "execution_id": execution_id,
                "task_id": task_id,
                "username": username,
                "chip_id": chip_id,
            }
        ).run()
        if doc is None:
            doc = cls(
                project_id=project_id,
                username=username,
                chip_id=chip_id,
                execution_id=execution_id,
                task_id=task_id,
                note=note,
            )
            doc.save()
            return doc

        doc.note = note
        doc.timestamp = now()
        doc.save()
        return doc

    model_config = ConfigDict(
        from_attributes=True,
    )
