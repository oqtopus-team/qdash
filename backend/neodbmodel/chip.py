from bunnet import Document
from pydantic import ConfigDict, Field

from ..datamodel.chip import ChipModel
from ..datamodel.coupling import CouplingModel
from ..datamodel.qubit import QubitModel
from ..datamodel.system_info import SystemInfoModel


class ChipDocument(Document):
    """Data model for a chip.

    Attributes:
        chip_id (str): The chip ID. e.g. "chip1".
        size (int): The size of the chip.
        qubits (dict): The qubits of the chip.
        couplings (dict): The couplings of the chip.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.
    """

    chip_id: str = Field(..., description="The chip ID")
    size: int = Field(..., description="The size of the chip")
    qubits: dict[str, QubitModel] = Field(..., description="The qubits of the chip")
    couplings: dict[str, CouplingModel] = Field(..., description="The couplings of the chip")

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "chip"
        indexes = [("chip_id")]

    @classmethod
    def from_domain(cls, domain: ChipModel, existing_doc: "ChipDocument") -> "ChipDocument":
        if existing_doc:
            existing_data = existing_doc.model_dump()
            domain_data = domain.model_dump()
            # not to overwrite qubits and couplings
            if "qubits" in existing_data:
                domain_data["qubits"] = existing_data["qubits"]
            if "couplings" in existing_data:
                domain_data["couplings"] = existing_data["couplings"]
            merged_data = {**existing_data, **domain_data}
            return cls(**merged_data)
        else:
            # create new document
            return cls(**domain.model_dump())

    def to_domain(self) -> ChipModel:
        return ChipModel(**self.model_dump())
