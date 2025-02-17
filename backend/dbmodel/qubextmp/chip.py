from bunnet import Document
from pydantic import BaseModel, ConfigDict

from .coupling import BaseCouplingSchema
from .qubit import BaseQubitSchema
from .system_info import SystemInfo


class BaseChipSchema(BaseModel):
    chip_id: str
    size: int
    qubits: dict[str, BaseQubitSchema]
    couplings: dict[str, BaseCouplingSchema]
    calibrated_at: str

    system_info: SystemInfo


class ChipDocument(Document):
    chip_id: str
    size: int
    qubits: dict[str, BaseQubitSchema]
    couplings: dict[str, BaseCouplingSchema]
    calibrated_at: str

    system_info: SystemInfo

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        name = "chip"
        indexes = [("chip_id")]

    @classmethod
    def from_domain(cls, domain: BaseChipSchema, existing_doc: "ChipDocument") -> "ChipDocument":
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

    def to_domain(self) -> BaseChipSchema:
        return BaseChipSchema(**self.model_dump())
