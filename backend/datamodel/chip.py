from datamodel.coupling import CouplingModel
from datamodel.qubit import QubitModel
from datamodel.system_info import SystemInfoModel
from pydantic import BaseModel, Field


class ChipModel(BaseModel):
    """Data model for a chip.

    Attributes
    ----------
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
