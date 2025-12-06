from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionCounterDocument(Document):
    """Document for the execution counter."""

    project_id: str | None = Field(None, description="Owning project identifier")
    date: str
    username: str
    chip_id: str
    index: int
    system_info: SystemInfoModel = Field(default_factory=SystemInfoModel, description="The system information")

    class Settings:
        """Settings for the document."""

        name = "execution_counter"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("date", ASCENDING), ("username", ASCENDING), ("chip_id", ASCENDING)],
                unique=True,
            )
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_next_index(cls, date: str, username: str, chip_id: str, project_id: str | None = None) -> int:
        """Get the next index for the given date, username and chip_id combination.

        Uses atomic findAndModify to prevent race conditions in concurrent executions.
        Index starts from 0 on the first call for a given date/username/chip_id combination.

        Args:
        ----
            date: The date to get the next index for
            username: The username to get the next index for
            chip_id: The chip_id to get the next index for
            project_id: The project_id to get the next index for

        Returns:
        -------
            The next index (0 on first call, then 1, 2, 3...)

        """
        import time

        from pymongo import ReturnDocument
        from pymongo.errors import DuplicateKeyError

        max_retries = 5
        for attempt in range(max_retries):
            # First, try to find existing document
            doc = cls.find_one({"project_id": project_id, "date": date, "username": username, "chip_id": chip_id}).run()

            if doc is None:
                # Try to create initial document with index 0
                try:
                    doc = cls(project_id=project_id, date=date, username=username, chip_id=chip_id, index=0)
                    doc.insert()
                    return 0
                except DuplicateKeyError:
                    # Another process created it concurrently
                    # Wait a bit and retry the whole operation
                    time.sleep(0.01 * (attempt + 1))
                    continue

            # Document exists - use atomic increment
            result = cls.get_motor_collection().find_one_and_update(
                {"project_id": project_id, "date": date, "username": username, "chip_id": chip_id},
                {"$inc": {"index": 1}},
                return_document=ReturnDocument.AFTER,
            )

            if result is not None:
                return result["index"]

            # Result was None, retry
            time.sleep(0.01 * (attempt + 1))

        # All retries failed
        msg = f"Failed to get next index after {max_retries} attempts"
        raise RuntimeError(msg)
