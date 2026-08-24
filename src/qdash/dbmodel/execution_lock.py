from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.datamodel.system_info import SystemInfoModel


class ExecutionLockDocument(Document):
    """Document for the execution lock."""

    project_id: str = Field(..., description="Owning project identifier")
    locked: bool = Field(default=False, description="Whether the execution is locked")
    execution_id: str | None = Field(
        default=None, description="Execution that currently owns the lock"
    )
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
        """Get the lock status for a project, creating an unlocked record if absent."""
        doc = cls.find_one({"project_id": project_id}).run()
        if doc is None:
            doc = cls(project_id=project_id, locked=False)
            doc.save()
            return False
        return doc.locked

    @classmethod
    def set_lock(cls, lock: bool, project_id: str, execution_id: str | None = None) -> None:
        """Set the lock state for a project, recording or clearing the owning execution.

        When locking, ``execution_id`` is stored as the owner. When unlocking,
        the stored owner is always reset to ``None`` regardless of the value
        passed in.
        """
        doc = cls.find_one({"project_id": project_id}).run()
        owner = execution_id if lock else None
        if doc is None:
            doc = cls(project_id=project_id, locked=lock, execution_id=owner)
            doc.save()
            return
        doc.locked = lock
        doc.execution_id = owner
        doc.save()

    @classmethod
    def lock(cls, project_id: str, execution_id: str | None = None) -> None:
        """Acquire the lock for a project, optionally recording the owning execution."""
        cls.set_lock(lock=True, project_id=project_id, execution_id=execution_id)

    @classmethod
    def unlock(cls, project_id: str) -> None:
        """Release the lock for a project and clear the recorded owner."""
        cls.set_lock(lock=False, project_id=project_id)
