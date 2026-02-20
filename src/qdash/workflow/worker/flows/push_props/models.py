from pydantic import BaseModel, Field


class QubitProperties(BaseModel):
    resonator_frequency: float | None = None
    qubit_frequency: float | None = None
    anharmonicity: float | None = None
    external_loss_rate: float | None = None
    internal_loss_rate: float | None = None
    t1: float | None = None
    t1_average: float | None = None
    t2_echo: float | None = None
    t2_echo_average: float | None = None
    t2_star: float | None = None
    average_readout_fidelity: float | None = None
    average_gate_fidelity: float | None = None
    x90_gate_fidelity: float | None = None
    x180_gate_fidelity: float | None = None


class CouplingProperties(BaseModel):
    static_zz_interaction: float | None = None
    qubit_qubit_coupling_strength: float | None = None
    zx90_gate_fidelity: float | None = None
    bell_state_fidelity: float | None = None


class ChipProperties(BaseModel):
    qubits: dict[str, QubitProperties] = Field(default_factory=dict)
    couplings: dict[str, CouplingProperties] = Field(default_factory=dict)
