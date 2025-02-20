from bunnet import Document
from datamodel.coupling import CouplingModel, EdgeInfoModel
from datamodel.system_info import SystemInfoModel
from pydantic import ConfigDict, Field


class CouplingDocument(Document):
    """Coupling document.

    Attributes
    ----------
        qid (str): The coupling ID. e.g. "0-1".
        chip_id (str): The chip ID. e.g. "chip1".
        data (dict): The data of the coupling. e.g. {"coupling_strength": 0.1}.
        calibrated_at (str): The time when the coupling was calibrated. e.g. "2021-01-01T00:00:00Z".
        edge_info (EdgeInfoModel): The edge information. e.g. {"fill": "red", "position": {"x": 0.0, "y": 0.0}}.
        system_info (SystemInfo): The system information. e.g. {"created_at": "2021-01-01T00:00:00Z", "updated_at": "2021-01-01T00:00:00Z"}.

    """

    qid: str = Field(..., description="The coupling ID")
    chip_id: str = Field(..., description="The chip ID")
    data: dict = Field(..., description="The data of the coupling")
    calibrated_at: str = Field(..., description="The time when the coupling was calibrated")
    edge_info: EdgeInfoModel = Field(..., description="The edge information")

    system_info: SystemInfoModel = Field(..., description="The system information")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Settings for the document."""

        name = "coupling"
        indexes = [("qid", "chip_id")]

    @classmethod
    def from_domain(
        cls, domain: CouplingModel, existing_doc: "CouplingDocument"
    ) -> "CouplingDocument":
        if existing_doc:
            existing_data = existing_doc.model_dump()
            domain_data = domain.model_dump()
            # not to overwrite edge_info
            if "edge_info" in existing_data:
                domain_data["node_info"] = existing_data["edge_info"]
            merged_data = {**existing_data, **domain_data}
            return cls(**merged_data)
        else:
            # create new document
            return cls(**domain.model_dump())

    def to_domain(self) -> CouplingModel:
        return CouplingModel(**self.model_dump())
