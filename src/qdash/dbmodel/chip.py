from datetime import datetime
from typing import ClassVar

from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from qdash.common.datetime_utils import now
from qdash.datamodel.note import NoteModel
from qdash.datamodel.system_info import SystemInfoModel


class ChipDocument(Document):
    """Data model for a chip.

    Qubit and coupling data are stored in separate QubitDocument and CouplingDocument
    collections for scalability (256+ qubits).

    Attributes
    ----------
        project_id (str): The owning project identifier (required).
        chip_id (str): The chip ID. e.g. "chip1".
        size (int): The size of the chip.
        installed_at (str): The time when the system information was created.
        system_info (SystemInfo): The system information.

    """

    project_id: str = Field(..., description="Owning project identifier")
    chip_id: str = Field("SAMPLE", description="The chip ID")
    user_id: str | None = Field(default=None, description="Creator user ID")
    username: str = Field(..., description="Creator username snapshot")
    size: int = Field(64, description="The size of the chip")
    current_cooldown_id: str | None = Field(
        default=None,
        description=(
            "ID of the cool-down cycle the chip is currently loaded in. "
            "Updated by cool-down assign/unassign endpoints. None when the "
            "chip is not in any active cool-down."
        ),
    )
    topology_id: str | None = Field(
        None, description="Topology template ID (e.g., 'square-lattice-mux-64')"
    )
    installed_at: datetime = Field(
        default_factory=now,
        description="The time when the chip was installed",
    )
    note: NoteModel = Field(
        default_factory=NoteModel,
        description="Free-form user note attached to this chip",
    )

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "chip"
        indexes: ClassVar = [
            IndexModel(
                [("project_id", ASCENDING), ("chip_id", ASCENDING), ("username", ASCENDING)],
                unique=True,
            ),
            IndexModel(
                [("project_id", ASCENDING), ("username", ASCENDING), ("installed_at", DESCENDING)]
            ),
            IndexModel(
                [("project_id", ASCENDING), ("user_id", ASCENDING), ("installed_at", DESCENDING)]
            ),
        ]

    @classmethod
    def get_current_chip(cls, username: str) -> "ChipDocument":
        chip = cls.find_one({"username": username}, sort=[("installed_at", DESCENDING)]).run()
        if chip is None:
            raise ValueError(f"Chip not found for user {username}")
        return chip

    @classmethod
    def get_chip_by_id(cls, username: str, chip_id: str) -> "ChipDocument | None":
        """Get a specific chip by chip_id and username.

        Unlike get_current_chip which returns the most recently installed chip,
        this method returns the chip with the specified chip_id.

        Args:
            username: The username of the chip owner
            chip_id: The specific chip ID to retrieve

        Returns:
            ChipDocument if found, None otherwise

        """
        return cls.find_one({"username": username, "chip_id": chip_id}).run()
