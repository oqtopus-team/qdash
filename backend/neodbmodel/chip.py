from bunnet import Document
from datamodel.coupling import CouplingModel
from datamodel.qubit import NodeInfoModel
from datamodel.system_info import SystemInfoModel
from pydantic import BaseModel, ConfigDict, Field


class QubitModel(BaseModel):
    """Model for a qubit.

    Attributes
    ----------
        qubit_id (str): The qubit ID. e.g. "0".
        status (str): The status of the qubit.
        data (dict): The data of the qubit.
        node_info (NodeInfo): The node information.

    """

    qid: str = Field(..., description="The qubit ID")
    status: str = Field("pending", description="The status of the qubit")
    data: dict = Field(..., description="The data of the qubit")
    node_info: NodeInfoModel = Field(..., description="The node information")


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
        indexes = [("chip_id")]

    def update_qubit(self, qid: str, qubit_data: dict) -> "ChipDocument":
        if not isinstance(qubit_data, QubitModel):
            qubit_data.pop("id", None)
            qubit_data = QubitModel(**qubit_data)
        self.qubits[qid] = qubit_data
        self.system_info.update_time()
        return self.save()
