"""Project-wide daily execution counters, independent of chip identity."""

import re
from contextlib import suppress
from typing import ClassVar

from bunnet import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError

from qdash.dbmodel.execution_counter import ExecutionCounterDocument


class ProjectExecutionCounterDocument(Document):
    """Allocate execution IDs in the same namespace as execution history."""

    project_id: str
    date: str
    index: int
    username: str
    user_id: str | None = None
    chip_ids: list[str] = Field(default_factory=list)

    class Settings:
        name = "project_execution_counter"
        indexes: ClassVar = [
            IndexModel([("project_id", ASCENDING), ("date", ASCENDING)], unique=True)
        ]

    @classmethod
    def get_next_index(
        cls,
        date: str,
        username: str,
        chip_id: str,
        project_id: str,
        user_id: str | None = None,
    ) -> int:
        """Atomically increment a shared counter, preserving legacy high-water marks.

        Upgrade all ID producers together: old workers still allocate chip-local IDs.
        Existing history is left untouched, including previously colliding IDs.
        """
        collection = cls.get_motor_collection()
        key = {"project_id": project_id, "date": date}
        if collection.find_one(key, {"_id": 1}) is None:
            legacy = ExecutionCounterDocument.get_motor_collection()
            highest = legacy.find_one(key, {"index": 1}, sort=[("index", -1)])
            initial_index = int(highest["index"]) if highest else -1
            # Also account for retained history if legacy counters were removed.
            pattern = rf"^{re.escape(date)}-([0-9]+)$"
            for name in ("execution_history", "task_result_history"):
                for record in collection.database[name].find(
                    {"project_id": project_id, "execution_id": {"$regex": pattern}},
                    {"execution_id": 1},
                ):
                    initial_index = max(
                        initial_index, int(record["execution_id"].rsplit("-", 1)[1])
                    )
            # Another producer may initialize the same project/date counter.
            with suppress(DuplicateKeyError):
                collection.update_one(
                    key,
                    {"$setOnInsert": {**key, "index": initial_index, "chip_ids": []}},
                    upsert=True,
                )

        result = collection.find_one_and_update(
            key,
            {
                "$inc": {"index": 1},
                "$set": {"username": username, "user_id": user_id},
                "$addToSet": {"chip_ids": chip_id},
            },
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("Project execution counter disappeared during allocation")
        return int(result["index"])
