"""Local synthetic qubit response for the QM backend's ``mock`` mode.

``QMMockDevice`` takes the place of the ``QuantumMachinesManager`` in mock mode. It
needs no QOP server, no account and none of the Quantum Machines packages: it
returns an averaged I/Q response computed with NumPy from a small model of one
qubit, so QDash's task, analysis, figure, raw data and persistence pipeline can run
end to end on any machine.

The model is deliberately minimal. For an amplitude scale ``a`` the excited-state
population of an ideal two-level system is ``(1 - cos(pi a / a_pi)) / 2``. The
averaged readout point moves on a straight line from the ground-state point
``iq_offset`` towards the excited-state point ``iq_offset + contrast * exp(i phase)``,
and each averaged point carries complex Gaussian noise whose standard deviation per
quadrature is ``noise_per_shot / sqrt(shots)``. There is no decoherence, leakage,
pulse distortion, QUA compilation or controller timing: a mock run verifies QDash's
pipeline and analysis, never the QUA program or the OPX.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

# Labels that mark every mock artifact, so a mock result can never pass as measured data.
QM_MOCK_SOURCE_TYPE = "qdash.qm.mock.rabi_iq"
QM_MOCK_VERSION = "QDash QM mock (local synthetic response, no QM SDK)"


class QMMockQubitSettings(BaseModel):
    """Parameters of the synthetic response of one qubit in mock mode."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    pi_amplitude_scale: float = Field(
        default=0.6, gt=0, lt=2, description="Amplitude scale that gives a pi rotation"
    )
    iq_offset: tuple[float, float] = Field(
        default=(0.010, 0.002), description="Averaged I/Q point of the ground state in V"
    )
    contrast: float = Field(
        default=0.015, gt=0, description="Distance in V between the ground and excited I/Q points"
    )
    phase_deg: float = Field(
        default=120.0, description="Direction in degrees of the excited state from the ground state"
    )
    noise_per_shot: float = Field(
        default=0.01,
        ge=0,
        description="Single-shot noise in V per quadrature; averaging divides it by sqrt(shots)",
    )

    def ideal_iq(self, amplitude_scales: npt.NDArray[np.float64]) -> npt.NDArray[np.complex128]:
        """Noise-free averaged I/Q response for each amplitude scale."""
        scales = np.asarray(amplitude_scales, dtype=float)
        population = (1.0 - np.cos(np.pi * scales / self.pi_amplitude_scale)) / 2.0
        ground = complex(*self.iq_offset)
        direction = self.contrast * np.exp(1j * math.radians(self.phase_deg))
        return np.asarray(ground + direction * population, dtype=np.complex128)

    def averaged_noise_std(self, shots: int) -> float:
        """Standard deviation per quadrature of one averaged point after ``shots`` shots."""
        if shots < 1:
            raise ValueError("shots must be a positive integer")
        return self.noise_per_shot / math.sqrt(shots)


class QMMockSettings(BaseModel):
    """The ``mock`` section of a QM settings file."""

    model_config = ConfigDict(extra="forbid")

    seed: int | None = Field(
        default=None,
        ge=0,
        description="Seed of the noise generator; omit it for different noise on every session",
    )
    qubits: dict[str, QMMockQubitSettings] = Field(min_length=1)

    @field_validator("qubits", mode="before")
    @classmethod
    def _string_qids(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(qid): settings or {} for qid, settings in value.items()}
        return value


class QMMockDevice:
    """Stand-in for ``QuantumMachinesManager`` that answers with a synthetic response.

    One device lives for one backend session. Its noise generator is seeded once, so
    a session with a fixed ``seed`` reproduces the same sequence of results.
    """

    def __init__(self, settings: QMMockSettings) -> None:
        self._settings = settings
        self._rng = np.random.default_rng(settings.seed)
        self._closed = False

    @property
    def closed(self) -> bool:
        """Whether the session that owns the device has ended."""
        return self._closed

    @property
    def seed(self) -> int | None:
        """Seed of the noise generator, recorded with every result."""
        return self._settings.seed

    def qubit(self, qid: str) -> QMMockQubitSettings:
        """Return the mock parameters of ``qid`` or fail with the configured qubit IDs."""
        try:
            return self._settings.qubits[qid]
        except KeyError:
            configured = ", ".join(sorted(self._settings.qubits)) or "none"
            raise ValueError(
                f"Qubit {qid} is not configured in the QM mock settings (configured: {configured})"
            ) from None

    def rabi_iq(
        self, qid: str, amplitude_scales: npt.NDArray[np.float64], shots: int
    ) -> npt.NDArray[np.complex128]:
        """Return the averaged I/Q response of ``qid`` to an amplitude sweep, in V."""
        if self._closed:
            raise RuntimeError("The QM mock session is closed; connect the backend again")
        params = self.qubit(qid)
        ideal = params.ideal_iq(amplitude_scales)
        std = params.averaged_noise_std(shots)
        noise = self._rng.standard_normal(ideal.size) + 1j * self._rng.standard_normal(ideal.size)
        return np.asarray(ideal + std * noise, dtype=np.complex128)

    def close(self) -> None:
        """End the session; later calls to ``rabi_iq`` fail."""
        self._closed = True
