from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionCounterDocument(Document):
    """Document for the execution counter."""

    date: str
    index: int
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="The system information"
    )

    class Settings:
        """Settings for the document."""

        name = "execution_counter"
        indexes: ClassVar = [IndexModel([("date", ASCENDING)], unique=True)]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_next_index(cls, date: str) -> int:
        doc = cls.find_one({"date": date}).run()
        if doc is None:
            doc = cls(date=date, index=0)
            doc.save()
            return 0
        doc.index += 1
        doc.save()
        return doc.index
