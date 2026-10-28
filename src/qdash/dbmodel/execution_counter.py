from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument


class ExecutionCounterDocument(Document):
    """Document for the execution counter."""

    project_id: str = Field(..., description="Owning project identifier")
    date: str
    user_id: str | None = None
    username: str
    chip_id: str
    index: int
    system_info: SystemInfoModel = Field(
        default_factory=SystemInfoModel, description="The system information"
    )

    class Settings:
        """Settings for the document."""

        name = "execution_counter"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("date", ASCENDING),
                    ("chip_id", ASCENDING),
                ],
                unique=True,
            )
        ]

    model_config = ConfigDict(
        from_attributes=True,
    )

    @staticmethod
    def _user_id_for_username(username: str) -> str | None:
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    @classmethod
    def get_next_index(
        cls,
        date: str,
        username: str,
        chip_id: str,
        project_id: str,
        user_id: str | None = None,
    ) -> int:
        """Allocate from the project-wide counter; retain legacy rows for lookup."""
        from qdash.dbmodel.project_execution_counter import ProjectExecutionCounterDocument

        return ProjectExecutionCounterDocument.get_next_index(
            date=date,
            username=username,
            chip_id=chip_id,
            project_id=project_id,
            user_id=user_id or cls._user_id_for_username(username),
        )
