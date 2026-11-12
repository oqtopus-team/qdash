"""Adapter around the Rabi experiment of ``qualang-tools``.

The QUA program comes from ``QUA_calibrations`` in
``qualang_tools.addons.calibration.calibrations`` (py-qua-tools, BSD-3-Clause,
Copyright (c) 2021 Q.M. Technologies Ltd.), installed as a dependency and not
copied here. This module only configures that class, runs it, and converts its
results:

* Hardware: ``QUA_calibrations.run_calibrations`` executes the program on an open
  quantum machine. The quantum machine is wrapped so the adapter can also fetch the
  averaged I/Q streams of the same job; the library itself keeps only magnitude and
  detrended phase.
* Simulator: ``QUA_calibrations.simulate_calibrations`` builds the same program but
  plots the result with matplotlib for a controller named ``con1`` and does not
  return the job. The adapter therefore builds the program the way that method does
  (``simulation = True`` and ``_rabi``) and calls ``QuantumMachinesManager.simulate``
  itself, keeping the simulated controller output samples. The simulated time is
  bounded by ``simulation.duration_ns``; ``simulate_rabi`` refuses a sweep whose
  first averaging iteration is estimated not to fit in it. Actual sweep coverage in
  the returned waveforms must be checked by the caller.
* Mock: no QUA program exists. ``run_rabi_on_mock`` asks the session's local
  ``QMMockDevice`` for a synthetic averaged I/Q response and returns it in the same
  ``RabiIQResult`` shape as hardware data, labelled ``mode="mock"``, so both go
  through the same fit, validation, figure and raw data code.

Signed sweeps: the model ``offset + A cos(2 pi f a)`` is even in the amplitude scale
``a``, so a sweep covers the pi rotation when the fitted pi scale lies within the
magnitudes ``|a|`` the sweep spans (see ``covered_magnitude_range``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import numpy.typing as npt

from qdash.workflow.engine.backend.qm import QM_INSTALL_HINT, QMDependencyError, import_qm_sdk
from qdash.workflow.engine.backend.qm_mock import QM_MOCK_SOURCE_TYPE, QMMockDevice

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qm import QMQubitSettings, QMSession

# QUA ``amp()`` scales accept values in [-2, 2).
AMPLITUDE_SCALE_MIN = -2.0
AMPLITUDE_SCALE_MAX = 2.0
CLOCK_CYCLE_NS = 4
# QUA_calibrations rejects cooldown times shorter than 4 clock cycles.
MIN_COOLDOWN_CYCLES = 4
RABI_CALIBRATION = "Rabi"
HARDWARE_SOURCE_TYPE = "qualang_tools.QUA_calibrations.Rabi"
# Headroom on the estimated sweep time for program start-up and QUA scheduling gaps,
# which the pulse-length estimate leaves out.
SIMULATION_HEADROOM_FACTOR = 1.25
SIMULATION_HEADROOM_NS = 1_000


@dataclass(frozen=True)
class RabiSweep:
    """Validated sweep of the amplitude scale applied to the qubit operation."""

    amplitude_scales: npt.NDArray[np.float64]
    shots: int
    cooldown_ns: int

    @classmethod
    def create(cls, amplitude_scales: Any, shots: Any, cooldown_ns: Any) -> RabiSweep:
        """Validate run parameters against the limits of the QUA program."""
        scales = np.asarray(amplitude_scales, dtype=float)
        if scales.ndim != 1 or scales.size < 3:
            raise ValueError("amplitude_scale_range must contain at least 3 points")
        if not np.all(np.isfinite(scales)):
            raise ValueError("amplitude_scale_range must contain finite values")
        if scales.min() < AMPLITUDE_SCALE_MIN or scales.max() >= AMPLITUDE_SCALE_MAX:
            raise ValueError(
                "amplitude_scale_range values must lie in [-2, 2), the QUA amp() range"
            )
        steps = np.diff(scales)
        if np.any(steps <= 0) or not np.allclose(steps, steps[0], rtol=1e-6, atol=1e-12):
            raise ValueError("amplitude_scale_range must be evenly spaced and increasing")
        if isinstance(shots, bool) or int(shots) != shots or int(shots) < 1:
            raise ValueError("shots must be a positive integer")
        if isinstance(cooldown_ns, bool) or int(cooldown_ns) != cooldown_ns:
            raise ValueError("cooldown_time must be an integer number of ns")
        cooldown = int(cooldown_ns)
        if cooldown % CLOCK_CYCLE_NS or cooldown < MIN_COOLDOWN_CYCLES * CLOCK_CYCLE_NS:
            raise ValueError(
                "cooldown_time must be a multiple of 4 ns and at least "
                f"{MIN_COOLDOWN_CYCLES * CLOCK_CYCLE_NS} ns"
            )
        return cls(amplitude_scales=scales, shots=int(shots), cooldown_ns=cooldown)

    @property
    def cooldown_clock_cycles(self) -> int:
        """Cooldown in 4 ns clock cycles, the unit ``QUA_calibrations`` takes."""
        return self.cooldown_ns // CLOCK_CYCLE_NS

    def iteration_duration_ns(self, drive_ns: int, readout_ns: int) -> int:
        """Lower bound of the program time of one averaging iteration over all points.

        Each point plays the drive pulse, then the readout pulse, then waits the
        cooldown; QUA adds small scheduling gaps on top.
        """
        return int(self.amplitude_scales.size) * (drive_ns + readout_ns + self.cooldown_ns)


def covered_magnitude_range(scales: npt.NDArray[np.float64]) -> tuple[float, float]:
    """Return the interval of amplitude magnitudes ``|a|`` that a sweep spans.

    A sweep that crosses zero covers ``[0, max |a|]``; a one-sided sweep covers
    ``[min |a|, max |a|]``. Signed sweeps are supported because the Rabi response
    depends on ``|a|`` only.
    """
    scales = np.asarray(scales, dtype=float)
    magnitudes = np.abs(scales)
    high = float(magnitudes.max())
    if scales.min() <= 0.0 <= scales.max():
        return 0.0, high
    return float(magnitudes.min()), high


@dataclass
class RabiIQResult:
    """Averaged I/Q response of one amplitude sweep, measured or synthetic.

    ``mode`` says where the response came from: ``hardware`` for an OPX measurement,
    ``mock`` for the local synthetic response of mock mode. ``source_type`` labels
    the raw data artifact and ``metadata`` records how the response was produced.
    """

    qid: str
    target: str
    amplitude_scales: npt.NDArray[np.float64]
    iq: npt.NDArray[np.complex128]
    magnitude: npt.NDArray[np.float64]
    phase: npt.NDArray[np.float64]
    mode: Literal["hardware", "mock"] = "hardware"
    source_type: str = HARDWARE_SOURCE_TYPE
    shots: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RabiSimulationResult:
    """Controller output samples returned by the QOP simulator.

    The simulator models the OPX outputs only, so this result carries no qubit
    response and must not be used to derive calibration values.
    """

    qid: str
    qubit_element: str
    amplitude_scales: npt.NDArray[np.float64]
    duration_ns: int
    shots: int = 1
    iteration_ns: int = 0
    analog: dict[str, npt.NDArray[Any]] = field(default_factory=dict)
    analog_sampling_rate: dict[str, float] = field(default_factory=dict)
    digital: dict[str, npt.NDArray[np.bool_]] = field(default_factory=dict)
    mode: Literal["simulator"] = "simulator"

    def has_output(self) -> bool:
        """Whether any analog port produced a non-zero sample."""
        return any(np.any(np.abs(samples) > 0) for samples in self.analog.values())

    @property
    def simulated_iterations(self) -> int:
        """Averaging iterations that fit in the simulated time, at most ``shots``.

        Estimated from ``iteration_ns``, a lower bound of one iteration's duration.
        The simulator truncates the program at ``duration_ns``; a simulated run is a
        waveform check, not the averaged measurement a hardware run performs.
        """
        if self.iteration_ns <= 0:
            return 0
        return min(self.shots, self.duration_ns // self.iteration_ns)


@dataclass(frozen=True)
class RabiFit:
    """Fit of ``offset + amplitude * cos(2 pi frequency * a)`` to a Rabi sweep."""

    amplitude: float
    frequency: float
    offset: float
    r2: float
    frequency_error: float

    @property
    def pi_amplitude_scale(self) -> float:
        """Amplitude scale of a pi rotation, half a Rabi period."""
        return 0.5 / self.frequency

    @property
    def pi_amplitude_scale_error(self) -> float:
        """Standard error of ``pi_amplitude_scale`` propagated from the frequency."""
        return 0.5 * self.frequency_error / self.frequency**2

    def evaluate(self, scales: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Evaluate the fitted model."""
        return self.offset + self.amplitude * np.cos(2 * np.pi * self.frequency * scales)


class _JobRecordingMachine:
    """Quantum machine proxy that keeps the job ``QUA_calibrations`` executes."""

    def __init__(self, machine: Any) -> None:
        self._machine = machine
        self.job: Any | None = None

    def execute(self, program: Any, *args: Any, **kwargs: Any) -> Any:
        self.job = self._machine.execute(program, *args, **kwargs)
        return self.job

    def __getattr__(self, name: str) -> Any:
        return getattr(self._machine, name)


def _import_calibrations() -> Any:
    import_qm_sdk()
    try:
        from qualang_tools.addons.calibration import calibrations
    except ImportError as exc:
        raise QMDependencyError(QM_INSTALL_HINT) from exc
    return calibrations


def build_rabi_calibration(
    qua_config: dict[str, Any], qubit: QMQubitSettings, sweep: RabiSweep
) -> Any:
    """Create a ``QUA_calibrations`` instance configured for a 1D amplitude Rabi sweep."""
    calibrations = _import_calibrations()
    calibration = calibrations.QUA_calibrations(
        configuration=qua_config,
        readout=(qubit.readout_element, qubit.readout_operation),
        qubit=(qubit.qubit_element, qubit.qubit_operation),
        integration_weights=tuple(qubit.integration_weights),
        outputs=tuple(qubit.outputs),
    )
    calibration.set_rabi(
        scan_variables=[("amplitude", sweep.amplitude_scales)],
        iterations=sweep.shots,
        cooldown_time=sweep.cooldown_clock_cycles,
    )
    return calibration


def build_rabi_program(calibration: Any) -> Any:
    """Return the QUA program ``simulate_calibrations`` would build for the Rabi sweep."""
    calibration.simulation = True
    try:
        return calibration._rabi(scan_dimension=1)
    finally:
        calibration.simulation = False


def run_rabi_on_hardware(session: QMSession, qid: str, sweep: RabiSweep) -> RabiIQResult:
    """Execute the Rabi sweep on the OPX and return the averaged response."""
    if not session.is_hardware:
        raise RuntimeError("run_rabi_on_hardware needs a backend in hardware mode")
    settings = session.settings
    qubit = settings.qubit(qid)
    calibration = build_rabi_calibration(settings.qua_config, qubit, sweep)
    machine = session.manager.open_qm(settings.qua_config)
    recorder = _JobRecordingMachine(machine)
    try:
        # plot=None skips matplotlib; plot_options must be a dict in qualang-tools.
        calibration.run_calibrations(quantum_machine=recorder, plot=None, plot_options={})
        if recorder.job is None:
            raise RuntimeError("QUA_calibrations did not execute a program")
        iq = _fetch_iq_volts(recorder.job, settings.readout_pulse_length(qid))
    finally:
        machine.close()

    results = calibration.results[RABI_CALIBRATION]
    return RabiIQResult(
        qid=qid,
        target=qubit.qubit_element,
        amplitude_scales=sweep.amplitude_scales,
        iq=iq,
        magnitude=np.asarray(results["amplitude"], dtype=float),
        phase=np.asarray(results["phase"], dtype=float),
        shots=sweep.shots,
    )


def run_rabi_on_mock(session: QMSession, qid: str, sweep: RabiSweep) -> RabiIQResult:
    """Return the synthetic response of the local mock device for the Rabi sweep.

    Imports no QM package. The amplitude scales and shots of the sweep reach the
    mock model; the cooldown has no effect on a synthetic response.
    """
    if not session.is_mock or not isinstance(session.manager, QMMockDevice):
        raise RuntimeError("run_rabi_on_mock needs a backend in mock mode")
    device = session.manager
    params = device.qubit(qid)
    iq = device.rabi_iq(qid, sweep.amplitude_scales, sweep.shots)
    return RabiIQResult(
        qid=qid,
        target=f"mock-q{qid}",
        amplitude_scales=sweep.amplitude_scales,
        iq=iq,
        magnitude=np.abs(iq),
        phase=np.unwrap(np.angle(iq)),
        mode="mock",
        source_type=QM_MOCK_SOURCE_TYPE,
        shots=sweep.shots,
        metadata={
            "seed": device.seed,
            "pi_amplitude_scale": params.pi_amplitude_scale,
            "iq_offset": list(params.iq_offset),
            "contrast": params.contrast,
            "phase_deg": params.phase_deg,
            "noise_per_shot": params.noise_per_shot,
            "averaged_noise_std": params.averaged_noise_std(sweep.shots),
        },
    )


def _fetch_iq_volts(job: Any, readout_length_ns: int) -> npt.NDArray[np.complex128]:
    """Fetch the averaged I/Q streams and convert them to volts as qualang-tools does."""
    from qualang_tools.units import unit

    handles = job.result_handles
    handles.wait_for_all_values()
    u = unit()
    i_data = np.asarray(u.demod2volts(handles.get("I").fetch_all(), readout_length_ns), float)
    q_data = np.asarray(u.demod2volts(handles.get("Q").fetch_all(), readout_length_ns), float)
    return i_data + 1j * q_data


def simulate_rabi(session: QMSession, qid: str, sweep: RabiSweep) -> RabiSimulationResult:
    """Simulate the Rabi program on the QOP simulator and return the output samples."""
    if not session.is_simulator:
        raise RuntimeError("simulate_rabi needs a backend in simulator mode")
    settings = session.settings
    qubit = settings.qubit(qid)
    duration_ns = settings.simulation.duration_ns
    iteration_ns = sweep.iteration_duration_ns(
        settings.drive_pulse_length(qid), settings.readout_pulse_length(qid)
    )
    required_ns = math.ceil(iteration_ns * SIMULATION_HEADROOM_FACTOR) + SIMULATION_HEADROOM_NS
    if required_ns > duration_ns:
        raise ValueError(
            f"One sweep of {sweep.amplitude_scales.size} points takes at least {iteration_ns} ns "
            f"({required_ns} ns with scheduling headroom) but simulation.duration_ns is "
            f"{duration_ns} ns, so the simulator would not reach "
            "every amplitude; use fewer points or a shorter cooldown_time (see "
            "simulator_run_parameters) or raise simulation.duration_ns"
        )
    qm = import_qm_sdk()
    calibration = build_rabi_calibration(settings.qua_config, qubit, sweep)
    program = build_rabi_program(calibration)
    simulation = qm.SimulationConfig(duration=settings.simulation.duration_clock_cycles)
    job = session.manager.simulate(settings.qua_config, program, simulation)
    samples = job.get_simulated_samples()

    result = RabiSimulationResult(
        qid=qid,
        qubit_element=qubit.qubit_element,
        amplitude_scales=sweep.amplitude_scales,
        duration_ns=duration_ns,
        shots=sweep.shots,
        iteration_ns=iteration_ns,
    )
    for controller, controller_samples in samples.items():
        rates = controller_samples.analog_sampling_rate
        for port, values in controller_samples.analog.items():
            key = f"{controller}:{port}"
            result.analog[key] = np.asarray(values)
            # The SDK defaults unspecified ports to 1 GS/s.
            result.analog_sampling_rate[key] = float(rates.get(str(port)) or 1e9)
        for port, values in controller_samples.digital.items():
            result.digital[f"{controller}:{port}"] = np.asarray(values, dtype=bool)
    return result


def project_iq(iq: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64]:
    """Project I/Q points onto their principal axis, the direction of largest variance."""
    points = np.column_stack([iq.real, iq.imag])
    centered = points - points.mean(axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    return np.asarray(centered @ vh[0], dtype=float)


def fit_amplitude_rabi(scales: npt.NDArray[np.float64], signal: npt.NDArray[np.float64]) -> RabiFit:
    """Fit ``offset + amplitude * cos(2 pi frequency * a)`` to a Rabi amplitude sweep.

    The rotation angle is proportional to the amplitude scale and is zero at zero
    amplitude, so the model has no phase term. A frequency grid search with linear
    least squares gives the starting point for a nonlinear refinement.
    """
    from scipy.optimize import curve_fit

    scales = np.asarray(scales, dtype=float)
    signal = np.asarray(signal, dtype=float)
    if scales.shape != signal.shape or scales.size < 4:
        raise ValueError("Rabi fit needs matching scale and signal arrays of 4 or more points")

    span = float(np.max(np.abs(scales)))
    step = float(np.min(np.diff(np.sort(scales))))
    if span <= 0 or step <= 0:
        raise ValueError("Rabi fit needs a non-degenerate amplitude sweep")

    best: tuple[float, float, float, float] | None = None
    for frequency in np.linspace(0.1 / span, 0.5 / step, 2000):
        design = np.column_stack([np.cos(2 * np.pi * frequency * scales), np.ones_like(scales)])
        coefficients, _, _, _ = np.linalg.lstsq(design, signal, rcond=None)
        residual = float(np.sum((design @ coefficients - signal) ** 2))
        if best is None or residual < best[0]:
            best = (residual, float(coefficients[0]), float(frequency), float(coefficients[1]))
    assert best is not None

    def model(a: Any, amplitude: float, frequency: float, offset: float) -> Any:
        return offset + amplitude * np.cos(2 * np.pi * frequency * a)

    try:
        popt, pcov = curve_fit(model, scales, signal, p0=best[1:], maxfev=10_000)
        amplitude, frequency, offset = (float(v) for v in popt)
        frequency_error = float(np.sqrt(pcov[1, 1])) if np.isfinite(pcov[1, 1]) else math.inf
    except RuntimeError:
        amplitude, frequency, offset = best[1:]
        frequency_error = math.inf
    frequency = abs(frequency)

    residuals = signal - model(scales, amplitude, frequency, offset)
    total = float(np.sum((signal - signal.mean()) ** 2))
    r2 = 1.0 - float(np.sum(residuals**2)) / total if total > 0 else 0.0
    return RabiFit(
        amplitude=amplitude,
        frequency=frequency,
        offset=offset,
        r2=r2,
        frequency_error=frequency_error,
    )
