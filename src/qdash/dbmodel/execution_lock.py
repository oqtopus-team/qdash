from typing import ClassVar

from bunnet import Document
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from qdash.common.utils.datetime import now
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionLockClaim(BaseModel):
    """One execution's hardware-resource claim."""

    execution_id: str | None = None
    chip_id: str = ""
    resources: list[str] = Field(default_factory=list)
    exclusive: bool = False


class ExecutionLockDocument(Document):
    """Document for the execution lock."""

    project_id: str = Field(..., description="Owning project identifier")
    locked: bool = Field(default=False, description="Whether the execution is locked")
    execution_id: str | None = Field(
        default=None, description="Execution that currently owns the lock"
    )
    claims: list[ExecutionLockClaim] = Field(
        default_factory=list, description="Concurrent hardware-resource claims"
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
        timestamp = now()
        cls.get_motor_collection().update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "locked": lock,
                    "execution_id": execution_id if lock else None,
                    "claims": [],
                    "system_info.updated_at": timestamp,
                },
                "$setOnInsert": {"system_info.created_at": timestamp},
            },
            upsert=True,
        )

    @classmethod
    def try_lock(
        cls,
        project_id: str,
        execution_id: str | None = None,
        chip_id: str = "",
        resources: tuple[str, ...] = (),
        exclusive: bool = True,
    ) -> bool:
        """Acquire the lock atomically, unless another execution holds it.

        Reacquisition checks conflicts in the same atomic update as acquisition.
        Additional scopes are retained until the execution releases all its claims.
        A missing execution ID never identifies an existing owner. Legacy locks
        without claims remain project-wide until their owner releases them.
        A conflicting upsert is rejected by the unique project index.
        """
        collection = cls.get_motor_collection()
        timestamp = now()
        if execution_id is not None:
            # Preserve a legacy owner's project-wide reservation without trusting
            # a separately read snapshot of ownership.
            result = collection.update_one(
                {
                    "project_id": project_id,
                    "locked": True,
                    "execution_id": execution_id,
                    "$or": [
                        {"claims": {"$exists": False}},
                        {"claims": {"$size": 0}},
                    ],
                },
                {"$set": {"system_info.updated_at": timestamp}},
            )
            if result.matched_count:
                return True

        conflict: dict[str, object] = {}
        if execution_id is not None:
            conflict["execution_id"] = {"$ne": execution_id}
        if chip_id:
            conflict["chip_id"] = {"$in": ["", chip_id]}
        if not exclusive:
            conflict["$or"] = [
                {"exclusive": True},
                {"resources": {"$in": list(resources)}},
            ]
        query: dict[str, object] = {
            "project_id": project_id,
            "$and": [
                {"$or": [{"claims.0": {"$exists": True}}, {"locked": False}]},
                {"claims": {"$not": {"$elemMatch": conflict}}},
            ],
        }
        # Raw pymongo bypasses Bunnet encoding, so system_info is written explicitly.
        try:
            collection.update_one(
                query,
                {
                    "$set": {
                        "locked": True,
                        "execution_id": execution_id,
                        "system_info.updated_at": timestamp,
                    },
                    "$addToSet": {
                        "claims": {
                            "execution_id": execution_id,
                            "chip_id": chip_id,
                            "resources": list(resources),
                            "exclusive": exclusive,
                        }
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
    def unlock(cls, project_id: str, execution_id: str | None = None) -> None:
        """Release one execution claim, or every claim for legacy callers."""
        collection = cls.get_motor_collection()
        if execution_id is None:
            collection.update_one(
                {"project_id": project_id},
                {"$set": {"locked": False, "execution_id": None, "claims": []}},
            )
            return
        result = collection.update_one(
            {"project_id": project_id},
            {"$pull": {"claims": {"execution_id": execution_id}}},
        )
        if result.modified_count:
            collection.update_one(
                {"project_id": project_id, "claims": {"$size": 0}},
                {"$set": {"locked": False, "execution_id": None}},
            )
        else:
            collection.update_one(
                {
                    "project_id": project_id,
                    "execution_id": execution_id,
                    "$or": [
                        {"claims": {"$exists": False}},
                        {"claims": {"$size": 0}},
                    ],
                },
                {"$set": {"locked": False, "execution_id": None}},
            )
