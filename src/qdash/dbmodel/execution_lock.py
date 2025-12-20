from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionLockDocument(Document):
    """Document for the execution lock."""

    project_id: str = Field(..., description="Owning project identifier")
    locked: bool = Field(default=False, description="Whether the execution is locked")
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="The system information"
    )

    class Settings:
        """Settings for the document."""

        name = "execution_lock"
        indexes: ClassVar = [
            IndexModel([("project_id", ASCENDING)], unique=True),
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_lock_status(cls, project_id: str) -> bool:
        doc = cls.find_one({"project_id": project_id}).run()
        if doc is None:
            doc = cls(project_id=project_id, locked=False)
            doc.save()
            return False
        return doc.locked

    @classmethod
    def set_lock(cls, lock: bool, project_id: str) -> None:
        doc = cls.find_one({"project_id": project_id}).run()
        if doc is None:
            doc = cls(project_id=project_id, locked=lock)
            doc.save()
            return
        doc.locked = lock
        doc.save()

    @classmethod
    def lock(cls, project_id: str) -> None:
        cls.set_lock(lock=True, project_id=project_id)

    @classmethod
    def unlock(cls, project_id: str) -> None:
        cls.set_lock(lock=False, project_id=project_id)
