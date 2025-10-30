from typing import ClassVar

import pendulum
from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class CalibrationNoteDocument(Document):
    """Document for storing calibration notes.

    Attributes
    ----------
        username (str): The username of the user who created the note.
        chip_id (str): The chip ID associated with this note.
        execution_id (str): The execution ID associated with this note.
        task_id (str): The task ID associated with this note.
        note (dict): The calibration note data.
        timestamp (str): The time when the note was last updated.
        system_info (SystemInfoModel): The system information.

    """

    username: str = Field(..., description="The username of the user who created the note")
    chip_id: str = Field(..., description="The chip ID associated with this note")
    execution_id: str = Field(..., description="The execution ID associated with this note")
    task_id: str = Field(..., description="The task ID associated with this note")
    note: dict = Field(..., description="The calibration note data")
    timestamp: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the note was last updated",
    )
    system_info: SystemInfoModel = Field(default_factory=SystemInfoModel, description="The system information")

    class Settings:
        """Settings for the document."""

        name = "calibration_note"
        indexes: ClassVar = [
            IndexModel(
                [("execution_id", ASCENDING), ("task_id", ASCENDING), ("username", ASCENDING), ("chip_id", ASCENDING)],
                unique=True,
            ),
            IndexModel(
                [("chip_id", ASCENDING), ("timestamp", ASCENDING)],
                name="chip_id_timestamp_idx",
            ),
        ]

    @classmethod
    def upsert_note(
        cls,
        username: str,
        chip_id: str,
        execution_id: str,
        task_id: str,
        note: dict,
    ) -> "CalibrationNoteDocument":
        """Upsert a calibration note.

        Args:
        ----
            username (str): The username of the user who created the note.
            chip_id (str): The chip ID associated with this note.
            execution_id (str): The execution ID associated with this note.
            task_id (str): The task ID associated with this note.
            note (dict): The calibration note data.

        Returns:
        -------
            CalibrationNoteDocument: The upserted document.

        """
        doc = cls.find_one(
            {"execution_id": execution_id, "task_id": task_id, "username": username, "chip_id": chip_id}
        ).run()
        if doc is None:
            doc = cls(username=username, chip_id=chip_id, execution_id=execution_id, task_id=task_id, note=note)
            doc.save()
            return doc

        doc.note = note
        doc.timestamp = pendulum.now(tz="Asia/Tokyo").to_iso8601_string()
        doc.save()
        return doc

    model_config = ConfigDict(
        from_attributes=True,
    )
