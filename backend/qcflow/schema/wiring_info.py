from typing import Optional

from pydantic import BaseModel, Field


class Wiring(BaseModel):
    control: dict[str, dict[str, str]]
    readout: dict[str, dict[str, str]]
    bias: Optional[dict[str, dict[str, str]]] = Field(default=None, exclude=True)
    pump: Optional[dict[str, dict[str, str]]] = Field(default=None, exclude=True)


class WiringInfo(BaseModel):
    name: str
    wiring_dict: Wiring
