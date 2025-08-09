from bunnet import Document
from pydantic import ConfigDict, Field
from qdash.datamodel.system_info import SystemInfoModel


class ExecutionLockDocument(Document):
    """Document for the execution lock."""

    locked: bool = Field(default=False, description="Whether the execution is locked")
    system_info: SystemInfoModel = Field(default_factory=SystemInfoModel, description="The system information")

    class Settings:
        """Settings for the document."""

        name = "execution_lock"

    model_config = ConfigDict(
        from_attributes=True,
    )

    @classmethod
    def get_lock_status(cls) -> bool:
        doc = cls.find_one().run()
        if doc is None:
            doc = cls(locked=False)
            doc.save()
            return False
        return doc.locked

    @classmethod
    def set_lock(cls, lock: bool) -> None:  # noqa: FBT001
        doc = cls.find_one().run()
        if doc is None:
            doc = cls(locked=lock)
            doc.save()
        doc.locked = lock
        doc.save()

    @classmethod
    def lock(cls) -> None:
        cls.set_lock(lock=True)

    @classmethod
    def unlock(cls) -> None:
        cls.set_lock(lock=False)
