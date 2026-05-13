from typing import Any, ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.datetime_utils import local_now
from qdash.datamodel.qubit import QubitModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.user import UserDocument


class QubitHistoryDocument(Document):
    """Data model for qubit history.

    Attributes
    ----------
        project_id (str): The owning project identifier.
        qid (str): The qubit ID. e.g. "0".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the qubit.
        status (str): The status of the qubit.
        system_info (SystemInfo): The system information.
        recorded_date (str): The date when this history record was created (YYYYMMDD).

    """

    project_id: str = Field(..., description="Owning project identifier")
    user_id: str | None = Field(default=None, description="Creator user ID")
    username: str = Field(..., description="Creator username snapshot")
    qid: str = Field(..., description="The qubit ID")
    status: str = Field(..., description="The status of the qubit")
    chip_id: str = Field(..., description="The chip ID")
    data: dict[str, Any] = Field(..., description="The data of the qubit")
    cooldown_id: str = Field(
        default="",
        description=(
            "Cool-down cycle this snapshot belongs to (denormalized from chip.current_cooldown_id)."
        ),
    )
    system_info: SystemInfoModel = Field(..., description="The system information")
    recorded_date: str = Field(
        default_factory=lambda: local_now().strftime("%Y%m%d"),
        description="The date when this history record was created",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "qubit_history"
        indexes: ClassVar = [
            IndexModel(
                [
                    ("project_id", ASCENDING),
                    ("chip_id", ASCENDING),
                    ("qid", ASCENDING),
                    ("username", ASCENDING),
                    ("recorded_date", ASCENDING),
                ],
                unique=True,
            ),
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("recorded_date", DESCENDING)]
            ),
            IndexModel(
                [("project_id", ASCENDING), ("user_id", ASCENDING), ("recorded_date", DESCENDING)]
            ),
        ]

    @classmethod
    def _resolve_cooldown_id(cls, *, project_id: str | None, chip_id: str | None) -> str:
        """Look up the chip's current_cooldown_id at write time."""
        if not project_id or not chip_id:
            return ""
        from qdash.dbmodel.chip import ChipDocument

        chip = ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()
        if chip is None:
            return ""
        return getattr(chip, "current_cooldown_id", None) or ""

    @classmethod
    def _user_id_for_username(cls, username: str) -> str | None:
        user = UserDocument.find_one({"username": username}).run()
        return user.user_id if user else None

    @classmethod
    def create_history(cls, qubit: QubitModel) -> "QubitHistoryDocument":
        """Create a history record from a QubitDocument."""
        today = local_now().strftime("%Y%m%d")
        cooldown_id = cls._resolve_cooldown_id(project_id=qubit.project_id, chip_id=qubit.chip_id)
        username = qubit.username
        if username is None:
            msg = "QubitDocument.username is required to create history"
            raise ValueError(msg)
        user_id = qubit.user_id or cls._user_id_for_username(username)
        existing_history = cls.find_one(
            {
                "project_id": qubit.project_id,
                "chip_id": qubit.chip_id,
                "qid": qubit.qid,
                "username": username,
                "recorded_date": today,
            }
        ).run()
        if existing_history:
            history = existing_history
            history.user_id = user_id
            history.data = qubit.data
            history.status = qubit.status
            history.cooldown_id = cooldown_id
        else:
            # Create a new history record
            history = cls(
                project_id=qubit.project_id,
                user_id=user_id,
                username=username,
                qid=qubit.qid,
                status=qubit.status,
                chip_id=qubit.chip_id,
                data=qubit.data,
                cooldown_id=cooldown_id,
                system_info=SystemInfoModel(),
            )
        history.save()
        return history
