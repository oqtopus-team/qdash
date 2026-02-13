import logging
import time
from datetime import datetime
from typing import Any, ClassVar, cast

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from pymongo.errors import DuplicateKeyError
from qdash.common.datetime_utils import now
from qdash.datamodel.system_info import SystemInfoModel

logger = logging.getLogger(__name__)


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
        max_retries: int = 3,
    ) -> "CalibrationNoteDocument":
        """Upsert a calibration note atomically with retry logic.

        Uses MongoDB's find_one_and_update with upsert=True to ensure
        thread-safe operations during parallel calibration task execution.
        Implements retry logic to handle race conditions when multiple
        processes attempt to insert the same document simultaneously.

        Args:
        ----
            username (str): The username of the user who created the note.
            chip_id (str): The chip ID associated with this note.
            execution_id (str): The execution ID associated with this note.
            task_id (str): The task ID associated with this note.
            note (dict): The calibration note data.
            project_id (str): The project ID for multi-tenancy.
            max_retries (int): Maximum retry attempts for DuplicateKeyError.

        Returns:
        -------
            CalibrationNoteDocument: The upserted document.

        """
        from pymongo import ReturnDocument

        query = {
            "project_id": project_id,
            "execution_id": execution_id,
            "task_id": task_id,
            "username": username,
            "chip_id": chip_id,
        }

        timestamp = now()

        # Atomic upsert using find_one_and_update
        update = {
            "$set": {
                "note": note,
                "timestamp": timestamp,
            },
            "$setOnInsert": {
                "project_id": project_id,
                "execution_id": execution_id,
                "task_id": task_id,
                "username": username,
                "chip_id": chip_id,
            },
        }

        collection = cls.get_motor_collection()

        last_error: DuplicateKeyError | None = None
        for attempt in range(max_retries):
            try:
                result = collection.find_one_and_update(
                    query,
                    update,
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                return cast("CalibrationNoteDocument", cls.model_validate(result))
            except DuplicateKeyError as e:  # noqa: PERF203
                last_error = e
                logger.warning(
                    "DuplicateKeyError on upsert attempt %d/%d for %s, retrying...",
                    attempt + 1,
                    max_retries,
                    query,
                )
                # Brief sleep with exponential backoff before retry
                time.sleep(0.1 * (2**attempt))

        # All retries exhausted, raise the last error
        logger.error(
            "Failed to upsert calibration note after %d attempts: %s",
            max_retries,
            query,
        )
        raise last_error  # type: ignore[misc]

    model_config = ConfigDict(
        from_attributes=True,
    )
