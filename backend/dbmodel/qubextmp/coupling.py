from bunnet import Document
from pydantic import BaseModel, ConfigDict

from .system_info import SystemInfo


class BaseCouplingSchema(BaseModel):
    qid: str
    chip_id: str
    data: dict
    calibrated_at: str

    system_info: SystemInfo


class Position(BaseModel):
    x: float
    y: float


class EdgeInfo(BaseModel):
    fill: str
    position: Position


class CouplingDocument(Document):
    qid: str
    chip_id: str
    data: dict
    calibrated_at: str
    edge_info: EdgeInfo

    system_info: SystemInfo

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "coupling"
        indexes = [("qid", "chip_id")]

    @classmethod
    def from_domain(
        cls, domain: BaseCouplingSchema, existing_doc: "CouplingDocument"
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

    def to_domain(self) -> BaseCouplingSchema:
        return BaseCouplingSchema(**self.model_dump())
