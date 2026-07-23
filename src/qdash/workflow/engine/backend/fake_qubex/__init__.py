"""Pulse-level emulation helpers for Qubex experiments."""

from .simulation import (
    FakeExperiment,
    build_qxsimulator_system,
    filter_pulse_schedule_for_simulation,
    materialize_pulse_schedule_for_simulation,
)

try:
    from qubex import PulseSchedule, pulse
except ImportError:
    PulseSchedule = None  # type: ignore[assignment,unused-ignore]
    pulse = None  # type: ignore[assignment,unused-ignore]

Experiment = FakeExperiment

__all__ = [
    "Experiment",
    "FakeExperiment",
    "PulseSchedule",
    "build_qxsimulator_system",
    "filter_pulse_schedule_for_simulation",
    "materialize_pulse_schedule_for_simulation",
    "pulse",
]
