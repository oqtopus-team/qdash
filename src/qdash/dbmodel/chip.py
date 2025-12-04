from typing import ClassVar

import pendulum
from bunnet import Document
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from qdash.datamodel.coupling import CouplingModel
from qdash.datamodel.qubit import QubitModel
from qdash.datamodel.system_info import SystemInfoModel


class ChipDocument(Document):
    """Data model for a chip.

    Attributes
    ----------
        chip_id (str): The chip ID. e.g. "chip1".
        size (int): The size of the chip.
        qubits (dict): The qubits of the chip.
        couplings (dict): The couplings of the chip.
        installed_at (str): The time when the system information was created.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    chip_id: str = Field("SAMPLE", description="The chip ID")
    username: str = Field(..., description="The username of the user who created the chip")
    size: int = Field(64, description="The size of the chip")
    qubits: dict[str, QubitModel] = Field({}, description="The qubits of the chip")
    couplings: dict[str, CouplingModel] = Field({}, description="The couplings of the chip")
    installed_at: str = Field(
        default_factory=lambda: pendulum.now(tz="Asia/Tokyo").to_iso8601_string(),
        description="The time when the system information was created",
    )

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "chip"
        indexes: ClassVar = [IndexModel([("chip_id", ASCENDING), ("username")], unique=True)]

    def update_qubit(self, qid: str, qubit_data: QubitModel) -> "ChipDocument":
        if qid not in self.qubits:
            raise ValueError(f"Qubit {qid} not found in chip {self.chip_id}")
        self.qubits[qid] = qubit_data
        self.system_info.update_time()
        self.save()
        return self

    def update_coupling(self, qid: str, coupling_data: CouplingModel) -> "ChipDocument":
        if qid not in self.couplings:
            raise ValueError(f"Coupling {qid} not found in chip {self.chip_id}")
        self.couplings[qid] = coupling_data
        self.system_info.update_time()
        self.save()
        return self

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
