"""The virtual device simulated by the fake backend.

The fake backend's simulator (``FakeExperiment``) and the fake chip setup preset of the
chip configuration scaffolder describe the same 64-qubit, 16-MUX device. Both read its values
from this module so the configuration a preset writes always names the device the simulator
runs.

Per-qubit values are a pattern of ``FAKE_DEVICE_PATTERN_LENGTH`` entries indexed by physical
qubit number: qubit ``n`` takes entry ``n % FAKE_DEVICE_PATTERN_LENGTH``, so the four qubits of
every MUX share the same layout and a session on any subset of qubits sees each qubit with the
same parameters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

FAKE_DEVICE_QUBITS = 64
FAKE_DEVICE_QUBITS_PER_MUX = 4
FAKE_DEVICE_MUXES = FAKE_DEVICE_QUBITS // FAKE_DEVICE_QUBITS_PER_MUX
FAKE_DEVICE_TOPOLOGY_ID = "square-lattice-mux-64"

FAKE_QUBIT_FREQUENCIES: tuple[float, ...] = (7.157231, 8.032295, 7.812112, 6.944337)
FAKE_QUBIT_ANHARMONICITIES: tuple[float, ...] = (-0.393715, -0.487412, -0.421337, -0.365884)
FAKE_READOUT_FREQUENCIES: tuple[float, ...] = (6.752, 6.903, 6.844, 6.711)
FAKE_DEVICE_PATTERN_LENGTH = len(FAKE_QUBIT_FREQUENCIES)
FAKE_READOUT_AMPLITUDE = 0.2
FAKE_CONTROL_AMPLITUDE = 0.0125


def fake_device_value(values: Sequence[float], qubit: int) -> float:
    """The device value of physical qubit ``qubit``; the pattern repeats past its length."""
    return float(values[qubit % len(values)])
