from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionCounterDocument(Document):
    """Document for the execution counter."""

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
                [("date", ASCENDING), ("username", ASCENDING), ("chip_id", ASCENDING)],
                unique=True,
            )
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_next_index(cls, date: str, username: str, chip_id: str) -> int:
        """Get the next index for the given date, username and chip_id combination.

        Args:
        ----
            date: The date to get the next index for
            username: The username to get the next index for
            chip_id: The chip_id to get the next index for

        Returns:
        -------
            The next index

        """
        doc = cls.find_one({"date": date, "username": username, "chip_id": chip_id}).run()
        if doc is None:
            doc = cls(date=date, username=username, chip_id=chip_id, index=0)
            doc.save()
            return 0
        doc.index += 1
        doc.save()
        return doc.index
