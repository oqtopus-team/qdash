"""Schema definitions for device_topology router."""

from pydantic import BaseModel, Field


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
    calibrated_at: str


class FidelityCondition(BaseModel):
    """Condition for fidelity filtering."""

    min: float
    max: float
    is_within_24h: bool = True


class Condition(BaseModel):
    """Condition for filtering device topology."""

    coupling_fidelity: FidelityCondition
    qubit_fidelity: FidelityCondition
    readout_fidelity: FidelityCondition
    only_maximum_connected: bool = True


class DeviceTopologyRequest(BaseModel):
    """Request model for device topology."""

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
