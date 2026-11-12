"""QM fake backend (``qm-fake``): a local synthetic device response for QM tasks.

``QMFakeBackend`` lets the tasks of the ``qm`` backend run without an OPX, a QOP
server or any Quantum Machines package. The tasks, their analysis,
figures, raw data and persistence are the ones the ``qm`` backend uses; only the
device response is replaced. ``QMFakeDevice`` takes the place of the
``QuantumMachinesManager`` and returns an averaged I/Q response computed with NumPy
from a small model of one qubit.

The model is deliberately minimal. For an amplitude scale ``a`` the excited-state
population of an ideal two-level system is ``(1 - cos(pi a / a_pi)) / 2``. The
averaged readout point moves on a straight line from the ground-state point
``iq_offset`` towards the excited-state point ``iq_offset + contrast * exp(i phase)``,
and each averaged point carries complex Gaussian noise whose standard deviation per
quadrature is ``noise_per_shot / sqrt(shots)``. There is no decoherence, leakage,
pulse distortion, QUA program, QUA compilation, controller timing or wiring: a
``qm-fake`` run checks QDash's task, analysis and persistence pipeline, never a QUA
program, the OPX or its connections.

The settings file defaults to ``<config dir>/qm-config/<chip_id>/qm-fake.yaml``. The
``qm_fake_config_path`` session option or the ``QDASH_QM_FAKE_CONFIG`` environment
variable overrides that path. It holds the response of each qubit and nothing that
reaches a QOP server: ``mode``, ``connection``, ``simulation``, ``qua_config`` and
``qua_config_file`` are rejected.

The ``qm-fake`` backend is never a calibration source: ``is_hardware`` is ``False``,
so ``BackendSaver`` keeps its results in the run history only.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import numpy.typing as npt
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.qm import (
    QMConfigurationError,
    resolve_qm_settings_path,
    string_qids,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

QM_FAKE_BACKEND_NAME = "qm-fake"
QM_FAKE_SETTINGS_FILE_NAME = "qm-fake.yaml"
QM_FAKE_CONFIG_ENV = "QDASH_QM_FAKE_CONFIG"
QM_FAKE_CONFIG_OPTION = "qm_fake_config_path"
# Labels that mark every fake artifact, so a fake result can never pass as measured data.
QM_FAKE_SOURCE_TYPE = "qdash.qm_fake.rabi_iq"
QM_FAKE_VERSION = "qm-fake (QDash synthetic response, no QM SDK)"
# Settings of the qm backend that reach a QOP server; a qm-fake settings file must not set them.
QOP_ONLY_SETTINGS = ("mode", "connection", "simulation", "qua_config", "qua_config_file")


class QMFakeQubitSettings(BaseModel):
    """Parameters of the synthetic response of one qubit."""

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


class QMFakeSettings(BaseModel):
    """Validated contents of a ``qm-fake.yaml`` settings file."""

    model_config = ConfigDict(extra="forbid")

    seed: int | None = Field(
        default=None,
        ge=0,
        description="Seed of the noise generator; omit it for different noise on every session",
    )
    qubits: dict[str, QMFakeQubitSettings] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _reject_qop_settings(cls, data: Any) -> Any:
        # Checked before field validation, so a QOP server section copied from
        # qm.yaml gets this message instead of an "extra field" error.
        if isinstance(data, dict):
            present = [name for name in QOP_ONLY_SETTINGS if name in data]
            if present:
                raise ValueError(
                    "the qm-fake backend runs locally without a QOP server or a QUA "
                    f"configuration; remove {', '.join(present)}. Use backend 'qm' with "
                    "qm.yaml for the OPX or the QOP simulator"
                )
            if "mock" in data:
                raise ValueError(
                    "qm-fake settings hold seed and qubits at the top level; "
                    "move the contents of 'mock' up one level"
                )
        return data

    @field_validator("qubits", mode="before")
    @classmethod
    def _string_qids(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = {qid: settings or {} for qid, settings in value.items()}
        return string_qids(value)

    def qubit(self, qid: str) -> QMFakeQubitSettings:
        """Return the response parameters of ``qid`` or fail with the configured qubit IDs."""
        try:
            return self.qubits[qid]
        except KeyError:
            configured = ", ".join(sorted(self.qubits)) or "none"
            raise QMConfigurationError(
                f"Qubit {qid} is not configured for the qm-fake backend (configured: {configured})"
            ) from None


def load_qm_fake_settings(path: Path) -> QMFakeSettings:
    """Load and validate a ``qm-fake.yaml`` settings file."""
    if not path.is_file():
        raise QMConfigurationError(f"qm-fake settings file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise QMConfigurationError(f"qm-fake settings file must contain a mapping: {path}")
    try:
        return QMFakeSettings.model_validate(data)
    except ValueError as exc:
        raise QMConfigurationError(f"Invalid qm-fake settings in {path}: {exc}") from exc


def resolve_qm_fake_settings_path(config: dict[str, Any]) -> Path:
    """Return the ``qm-fake.yaml`` path for a session configuration."""
    return resolve_qm_settings_path(
        config,
        option=QM_FAKE_CONFIG_OPTION,
        env=QM_FAKE_CONFIG_ENV,
        file_name=QM_FAKE_SETTINGS_FILE_NAME,
    )


class QMFakeDevice:
    """Stand-in for ``QuantumMachinesManager`` that answers with a synthetic response.

    One device lives for one backend session. Its noise generator is seeded once, so
    a session with a fixed ``seed`` reproduces the same sequence of results.
    """

    def __init__(self, settings: QMFakeSettings) -> None:
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

    def qubit(self, qid: str) -> QMFakeQubitSettings:
        """Return the response parameters of ``qid``."""
        return self._settings.qubit(qid)

    def rabi_iq(
        self, qid: str, amplitude_scales: npt.NDArray[np.float64], shots: int
    ) -> npt.NDArray[np.complex128]:
        """Return the averaged I/Q response of ``qid`` to an amplitude sweep, in V."""
        if self._closed:
            raise RuntimeError("The qm-fake session is closed; connect the backend again")
        params = self.qubit(qid)
        ideal = params.ideal_iq(amplitude_scales)
        std = params.averaged_noise_std(shots)
        noise = self._rng.standard_normal(ideal.size) + 1j * self._rng.standard_normal(ideal.size)
        return np.asarray(ideal + std * noise, dtype=np.complex128)

    def close(self) -> None:
        """End the session; later calls to ``rabi_iq`` fail."""
        self._closed = True


@dataclass
class QMFakeSession:
    """Session handed to QM tasks by ``QMFakeBackend.get_instance``.

    It answers the same questions as ``QMSession`` (``mode``, ``is_hardware``,
    ``is_simulator``, ``is_fake``), so a QM task picks its path from the session alone.
    """

    device: QMFakeDevice
    settings: QMFakeSettings

    @property
    def mode(self) -> Literal["fake"]:
        """Execution mode of the session."""
        return "fake"

    @property
    def is_simulator(self) -> bool:
        """A fake session never runs the QOP simulator."""
        return False

    @property
    def is_fake(self) -> bool:
        """A fake session answers with a local synthetic response."""
        return True

    @property
    def is_hardware(self) -> bool:
        """A fake session never measures a device."""
        return False


class QMFakeBackend(BaseBackend):
    """Backend that runs QM tasks against ``QMFakeDevice`` instead of an OPX."""

    name: str = QM_FAKE_BACKEND_NAME

    def __init__(self, config: dict[str, Any]) -> None:
        """Store the session configuration; settings are read on first use."""
        self._config = config
        self._settings: QMFakeSettings | None = config.get("qm_fake_settings")
        self._device: QMFakeDevice | None = None

    @property
    def config(self) -> dict[str, Any]:
        """Session configuration passed by the orchestrator."""
        return self._config

    @property
    def settings(self) -> QMFakeSettings:
        """Validated qm-fake settings, loaded from the settings file on first access."""
        if self._settings is None:
            self._settings = load_qm_fake_settings(resolve_qm_fake_settings_path(self._config))
        return self._settings

    @property
    def mode(self) -> Literal["fake"]:
        """Execution mode, compared with the mode recorded in each result."""
        return "fake"

    @property
    def is_simulator(self) -> bool:
        """The fake backend never runs the QOP simulator."""
        return False

    @property
    def is_fake(self) -> bool:
        """The fake backend answers with a local synthetic response."""
        return True

    @property
    def is_hardware(self) -> bool:
        """Always ``False``: ``BackendSaver`` never writes fake results as calibration values."""
        return False

    def version(self) -> str:
        """Return the fake backend label; no QM SDK is involved."""
        return QM_FAKE_VERSION

    def connect(self) -> None:
        """Start a local ``QMFakeDevice``; no QM package and no network is used."""
        if self._device is not None:
            return
        settings = self.settings
        self._device = QMFakeDevice(settings)
        logger.info(
            "Started the qm-fake device (synthetic response, seed=%s); no QOP server is used",
            settings.seed,
        )

    def disconnect(self) -> None:
        """Close the device; safe to call repeatedly."""
        device, self._device = self._device, None
        if device is not None:
            device.close()

    @property
    def is_connected(self) -> bool:
        """Return whether a device is open."""
        return self._device is not None

    def get_instance(self) -> QMFakeSession:
        """Return the live session, starting the device first when needed."""
        if self._device is None:
            self.connect()
        if self._device is None:
            msg = "Backend instance is not initialized. Please call connect() first."
            raise RuntimeError(msg)
        return QMFakeSession(device=self._device, settings=self.settings)
