"""Schema definitions for device_topology router."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Position(BaseModel):
    """Position of the qubit on the device."""

    x: float
    y: float


class MeasError(BaseModel):
    """Measurement error of the qubit."""

    prob_meas1_prep0: float
    prob_meas0_prep1: float
    readout_assignment_error: float


class QubitLifetime(BaseModel):
    """Qubit lifetime of the qubit."""

    t1: float
    t2: float


class QubitGateDuration(BaseModel):
    """Gate duration of the qubit."""

    rz: int
    sx: int
    x: int


class Qubit(BaseModel):
    """Qubit information."""

    id: int
    physical_id: int
    position: Position
    fidelity: float
    meas_error: MeasError
    qubit_lifetime: QubitLifetime
    gate_duration: QubitGateDuration


class CouplingGateDuration(BaseModel):
    """Gate duration of the coupling."""

    rzx90: int


class Coupling(BaseModel):
    """Coupling information."""

    control: int
    target: int
    fidelity: float
    gate_duration: CouplingGateDuration


class Device(BaseModel):
    """Device information."""

    name: str
    device_id: str
    qubits: list[Qubit]
    couplings: list[Coupling]
    calibrated_at: datetime | str


class FidelityCondition(BaseModel):
    """Condition for fidelity filtering."""

    min: float
    max: float
    is_within_24h: bool = True
    metric: str | None = None


class Condition(BaseModel):
    """Condition for filtering device topology."""

    model_config = ConfigDict(extra="forbid")

    coupling_fidelity: FidelityCondition
    qubit_fidelity: FidelityCondition
    readout_fidelity: FidelityCondition
    cr_direction: Literal["forward", "inverse", "mix"] | None = Field(
        default="mix",
        description=(
            "Optional CR direction filter. "
            "forward uses the topology coupling order; inverse uses the reverse order; "
            "mix returns both available calibrated directions. "
            "When omitted, mix is used."
        ),
    )
    only_maximum_connected: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize_cr_direction_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "crDirection" in data and "cr_direction" not in data:
            normalized = dict(data)
            normalized["cr_direction"] = normalized.pop("crDirection")
            return normalized
        return data


class DeviceTopologyRequest(BaseModel):
    """Request model for device topology."""

    model_config = ConfigDict(extra="forbid")

    name: str = "anemone"
    device_id: str = "anemone"
    qubits: list[str] = ["0", "1", "2", "3", "4", "5"]
    exclude_couplings: list[str] = []
    condition: Condition = Field(
        default_factory=lambda: Condition(
            coupling_fidelity=FidelityCondition(min=0.0, max=1.0, is_within_24h=True),
            qubit_fidelity=FidelityCondition(min=0.0, max=1.0, is_within_24h=True),
            readout_fidelity=FidelityCondition(min=0.0, max=1.0, is_within_24h=True),
            only_maximum_connected=True,
        )
    )
