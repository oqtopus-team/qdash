from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from qdash.common.utils.datetime import now
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
    def try_lock(cls, project_id: str, execution_id: str | None = None) -> bool:
        """Acquire the lock atomically, unless another execution holds it.

        A lock already owned by ``execution_id`` is reacquired, which is how a
        flow run adopts the lock the API claimed for it at dispatch time.
        Otherwise the upsert only matches an unlocked record; when the project
        is locked it falls through to an insert that the unique index on
        ``project_id`` rejects, so a ``DuplicateKeyError`` is the "someone
        else holds it" answer rather than a failure.

        Parameters
        ----------
        project_id : str
            The project identifier
        execution_id : str | None
            The execution that will own the lock

        Returns
        -------
        bool
            True when the lock was acquired or already owned, False when held

        """
        query: dict[str, object] = {"project_id": project_id, "locked": False}
        if execution_id is not None:
            query = {
                "project_id": project_id,
                "$or": [{"locked": False}, {"execution_id": execution_id}],
            }
        # Raw pymongo bypasses Bunnet encoding, so system_info is written explicitly.
        timestamp = now()
        try:
            cls.get_motor_collection().update_one(
                query,
                {
                    "$set": {
                        "locked": True,
                        "execution_id": execution_id,
                        "system_info.updated_at": timestamp,
                    },
                    "$setOnInsert": {
                        "project_id": project_id,
                        "system_info.created_at": timestamp,
                    },
                },
                upsert=True,
            )
        except DuplicateKeyError:
            return False
        return True

    @classmethod
    def lock(cls, project_id: str, execution_id: str | None = None) -> None:
        """Acquire the lock for a project, optionally recording the owning execution."""
        cls.set_lock(lock=True, project_id=project_id, execution_id=execution_id)

    @classmethod
    def unlock(cls, project_id: str) -> None:
        """Release the lock for a project and clear the recorded owner."""
        cls.set_lock(lock=False, project_id=project_id)
