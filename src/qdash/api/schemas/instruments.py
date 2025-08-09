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
    port: int | None = Field(default=0)
    direction: str | None = Field(default="")
    lo_freq: float | None = Field(default=0)
    cnco_freq: float | None = Field(default=0)
    fullscale_current: int | None = Field(default=0)
    sideband: str | None = Field(default="")


class BoxDetailResponse(BoxStatus):
    detail: list[PortConfig] | None = Field(default=[])


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
