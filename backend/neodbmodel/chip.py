from typing import ClassVar

from bunnet import Document
from datamodel.coupling import CouplingModel
from datamodel.qubit import QubitModel
from datamodel.system_info import SystemInfoModel
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel


class ChipDocument(Document):
    """Data model for a chip.

    Attributes
    ----------
        chip_id (str): The chip ID. e.g. "chip1".
        size (int): The size of the chip.
        qubits (dict): The qubits of the chip.
        couplings (dict): The couplings of the chip.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    chip_id: str = Field("SAMPLE", description="The chip ID")
    username: str = Field(..., description="The username of the user who created the chip")
    size: int = Field(64, description="The size of the chip")
    qubits: dict[str, QubitModel] = Field({}, description="The qubits of the chip")
    couplings: dict[str, CouplingModel] = Field({}, description="The couplings of the chip")

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
