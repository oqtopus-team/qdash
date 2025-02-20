from bunnet import Document
from datamodel.qubit import NodeInfoModel, QubitModel
from datamodel.system_info import SystemInfoModel
from pydantic import ConfigDict, Field


class QubitDocument(Document):
    """Data model for a qubit.

    Attributes
    ----------
        qid (str): The qubit ID. e.g. "0".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the qubit. e.g. {"qubit_frequency": 5.0}.
        calibrated_at (str): The time when the qubit was calibrated. e.g. "2021-01-01T00:00:00Z".
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    qid: str = Field(..., description="The qubit ID")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the qubit")
    calibrated_at: str = Field(..., description="The time when the qubit was calibrated")
    node_info: NodeInfoModel = Field(..., description="The node information")

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "qubit"
        indexes = [("qid", "chip_id")]

    @classmethod
    def from_domain(cls, domain: QubitModel, existing_doc: "QubitDocument") -> "QubitDocument":
        if existing_doc:
            existing_data = existing_doc.model_dump()
            domain_data = domain.model_dump()
            # not to overwrite node_info
            if "node_info" in existing_data:
                domain_data["node_info"] = existing_data["node_info"]
            merged_data = {**existing_data, **domain_data}
            return cls(**merged_data)
        else:
            # create new document
            return cls(**domain.model_dump())

    def to_domain(self) -> QubitModel:
        return QubitModel(**self.model_dump())
