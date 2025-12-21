from datetime import datetime

from pydantic import BaseModel, Field
from qdash.datamodel.system_info import SystemInfoModel


class ChipModel(BaseModel):
    """Data model for a chip.

    Qubit and coupling data are stored in separate QubitDocument and CouplingDocument
    collections for scalability (256+ qubits).

    Attributes
    ----------
        chip_id (str): The chip ID. e.g. "chip1".
        size (int): The size of the chip.
        installed_at (datetime): The time when the chip was installed.
        system_info (SystemInfo): The system information.

    """

    project_id: str | None = Field(None, description="Owning project identifier")
    chip_id: str = Field(..., description="The chip ID")
    username: str = Field(..., description="The username of the user who created the chip")
    size: int = Field(..., description="The size of the chip")
    topology_id: str | None = Field(
        None, description="Topology template ID (e.g., 'square-lattice-mux-64')"
    )
    installed_at: datetime = Field(..., description="The time when the chip was installed")

    system_info: SystemInfoModel = Field(..., description="The system information")
