from bunnet import Document
from pydantic import BaseModel, ConfigDict

from .system_info import SystemInfo


class BaseQubitSchema(BaseModel):
    qid: str
    chip_id: str
    data: dict
    calibrated_at: str

    system_info: SystemInfo


class Position(BaseModel):
    x: float
    y: float


class NodeInfo(BaseModel):
    fill: str
    position: Position


class QubitDocument(Document):
    qid: str
    chip_id: str
    data: dict
    calibrated_at: str
    node_info: NodeInfo

    system_info: SystemInfo

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "qubit"
        indexes = [("qid", "chip_id")]

    @classmethod
    def from_domain(cls, domain: BaseQubitSchema, existing_doc: "QubitDocument") -> "QubitDocument":
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

    def to_domain(self) -> BaseQubitSchema:
        return BaseQubitSchema(**self.model_dump())
