from typing import ClassVar

import pendulum
from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel
from qdash.datamodel.coupling import CouplingModel
from qdash.datamodel.qubit import QubitModel
from qdash.datamodel.system_info import SystemInfoModel
from qdash.dbmodel.chip import ChipDocument


class ChipHistoryDocument(Document):
    """Data model for chip history.

    Attributes
    ----------
        chip_id (str): The chip ID. e.g. "chip1".
        size (int): The size of the chip.
        qubits (dict): The qubits of the chip.
        couplings (dict): The couplings of the chip.
        installed_at (str): The time when the system information was created.
        system_info (SystemInfo): The system information.
        recorded_date (str): The date when this history record was created (YYYY-MM-DD).

    """

    chip_id: str = Field(..., description="The chip ID")
    username: str = Field(..., description="The username of the user who created the chip")
    size: int = Field(..., description="The size of the chip")
    qubits: dict[str, QubitModel] = Field({}, description="The qubits of the chip")
    couplings: dict[str, CouplingModel] = Field({}, description="The couplings of the chip")
    installed_at: str = Field(..., description="The time when the system information was created")
    system_info: SystemInfoModel = Field(..., description="The system information")
    recorded_date: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").format("YYYY-MM-DD"),
        description="The date when this history record was created",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "chip_history"
        indexes: ClassVar = [
            IndexModel(
                [("chip_id", ASCENDING), ("username", ASCENDING), ("recorded_date", ASCENDING)],
                unique=True,
            )
        ]

    @classmethod
    def get_yesterday_history(cls, chip_id: str, username: str) -> "ChipHistoryDocument | None":
        """Get yesterday's history record for a chip.

        Parameters
        ----------
        chip_id : str
            The chip ID
        username : str
            The username of the user who created the chip

        Returns
        -------
        ChipHistoryDocument | None
            Yesterday's history record if it exists, None otherwise

        """
        yesterday = pendulum.now(tz="Asia/Tokyo").subtract(days=1).format("YYYY-MM-DD")
        return cls.find_one(
            {
                "chip_id": chip_id,
                "username": username,
                "recorded_date": yesterday,
            }
        ).run()

    @classmethod
    def create_history(cls, chip_doc: ChipDocument) -> "ChipHistoryDocument":
        """Create a history record from a ChipDocument."""
        today = pendulum.now(tz="Asia/Tokyo").format("YYYY-MM-DD")
        existing_history = cls.find_one(
            {
                "chip_id": chip_doc.chip_id,
                "username": chip_doc.username,
                "recorded_date": today,
            }
        ).run()
        if existing_history:
            history = existing_history
            history.qubits = chip_doc.qubits
            history.couplings = chip_doc.couplings
        else:
            history = cls(
                chip_id=chip_doc.chip_id,
                username=chip_doc.username,
                size=chip_doc.size,
                qubits=chip_doc.qubits,
                couplings=chip_doc.couplings,
                installed_at=chip_doc.installed_at,
                system_info=chip_doc.system_info,
            )
        history.save()
        return history
