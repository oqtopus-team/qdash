"""Test doubles for the Quantum Machines backend.

Nothing here talks to a QOP server. ``SyntheticRabiResponse`` is a made-up qubit
response used to exercise result handling and fitting; it is neither OPX hardware
data nor output of the official QOP simulator. ``StubQuantumMachinesManager`` stands
in for ``qm.QuantumMachinesManager`` so tests can check what the backend sends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from qdash.workflow.engine.backend.qm import QMBackend, QMBackendSettings, load_qm_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_SETTINGS_PATH = REPO_ROOT / "config" / "qm-config" / "example" / "qm.yaml"


def example_settings(mode: str = "simulator") -> QMBackendSettings:
    """Load the committed example settings with the requested mode."""
    return load_qm_settings(EXAMPLE_SETTINGS_PATH).model_copy(update={"mode": mode})


def connected_backend(manager: Any, mode: str = "simulator") -> QMBackend:
    """Return a QM backend that uses ``manager`` instead of a QOP connection."""
    backend = QMBackend({"chip_id": "example", "qm_settings": example_settings(mode)})
    backend._manager = manager
    return backend


@dataclass
class SyntheticRabiResponse:
    """Synthetic averaged I/Q response of an ideal qubit, for tests only."""

    pi_amplitude_scale: float = 0.6
    ground: complex = 0.010 + 0.002j
    excited: complex = -0.004 + 0.012j
    noise: float = 0.0
    seed: int = 7

    def iq(self, scales: np.ndarray) -> np.ndarray:
        population = (1 - np.cos(np.pi * scales / self.pi_amplitude_scale)) / 2
        values = self.ground + (self.excited - self.ground) * population
        if self.noise:
            rng = np.random.default_rng(self.seed)
            values = values + self.noise * (
                rng.standard_normal(scales.size) + 1j * rng.standard_normal(scales.size)
            )
        return np.asarray(values)


class _StubHandle:
    def __init__(self, values: np.ndarray) -> None:
        self._values = values

    def fetch_all(self) -> np.ndarray:
        return self._values


class _StubResultHandles:
    def __init__(self, streams: dict[str, np.ndarray]) -> None:
        self._streams = streams
        self.waited = False

    def wait_for_all_values(self) -> bool:
        self.waited = True
        return True

    def get(self, name: str) -> _StubHandle:
        return _StubHandle(self._streams[name])


class StubJob:
    """Job whose ``I``/``Q`` streams hold raw demodulated values."""

    def __init__(self, streams: dict[str, np.ndarray]) -> None:
        self.result_handles = _StubResultHandles(streams)


@dataclass
class StubQuantumMachine:
    """Records executed programs and answers with a synthetic Rabi response."""

    response: SyntheticRabiResponse
    scales: np.ndarray
    fail_execute: bool = False
    executed: list[Any] = field(default_factory=list)
    closed: int = 0

    def execute(self, program: Any) -> StubJob:
        if self.fail_execute:
            raise RuntimeError("execution failed")
        self.executed.append(program)
        iq = self.response.iq(self.scales)
        return StubJob({"I": iq.real, "Q": iq.imag, "iteration": np.array(0)})

    def close(self) -> None:
        self.closed += 1


@dataclass
class StubSimulatedJob:
    samples: Any

    def get_simulated_samples(self) -> Any:
        return self.samples


@dataclass
class StubQuantumMachinesManager:
    """Stand-in for ``qm.QuantumMachinesManager``; no QOP server is involved."""

    machine: StubQuantumMachine | None = None
    samples: Any = None
    simulated: list[tuple[Any, Any, Any]] = field(default_factory=list)
    opened_configs: list[dict[str, Any]] = field(default_factory=list)
    closed: int = 0

    def open_qm(self, config: dict[str, Any]) -> StubQuantumMachine:
        assert self.machine is not None
        self.opened_configs.append(config)
        return self.machine

    def simulate(self, config: Any, program: Any, simulation: Any) -> StubSimulatedJob:
        self.simulated.append((config, program, simulation))
        return StubSimulatedJob(self.samples)

    def close(self) -> None:
        self.closed += 1
