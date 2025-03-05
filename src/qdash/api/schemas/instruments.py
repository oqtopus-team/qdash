from typing import Optional

from pydantic import BaseModel, Field


class BoxStatus(BaseModel):
    label: str
    name: str
    type: str
    status: str
    address: str
    adapter: str


class BoxStatusResponse(BoxStatus):
    pass


class PortConfig(BaseModel):
    port: Optional[int] = Field(default=0)
    direction: Optional[str] = Field(default="")
    lo_freq: Optional[float] = Field(default=0)
    cnco_freq: Optional[float] = Field(default=0)
    fullscale_current: Optional[int] = Field(default=0)
    sideband: Optional[str] = Field(default="")


class BoxDetailResponse(BoxStatus):
    detail: Optional[list[PortConfig]] = Field(default=[])


class IQData(BaseModel):
    i: list[float]
    q: list[float]


class CaptureData(BaseModel):
    ports: dict[str, IQData]


class CaptureDataResponse(IQData):
    pass


class InitLSIResponse(BaseModel):
    message: str


class UpdatePortConfig(BaseModel):
    port: int
    sideband: str
    vatt: int
