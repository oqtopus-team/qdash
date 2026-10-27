"""Spin-lock relaxation spectroscopy task."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import numpy.typing as npt
from qubex.core import DataModel
from qubex.experiment.experiment_constants import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    import plotly.graph_objects as go

    from qdash.workflow.engine.backend.qubex import QubexBackend


DEFAULT_DURATION_RANGE = np.geomspace(100.0, 200e3, 21)
logger = logging.getLogger(__name__)


class SpinLockSpectroscopyData(DataModel):
    """NetCDF artifact containing spin-lock data needed for later reanalysis."""

    target: str
    requested_rabi_frequencies: npt.NDArray[Any]
    accepted_rabi_frequencies: npt.NDArray[Any]
    rejected_rabi_frequencies: npt.NDArray[Any]
    duration_range: npt.NDArray[Any]
    total_pulse_duration_range: npt.NDArray[Any]
    ramp_duration: float
    drive_amplitudes: npt.NDArray[Any]
    rabi_frequencies: npt.NDArray[Any]
    expectation_labels: tuple[str, ...]
    mean_iq: npt.NDArray[Any]
    expectations: npt.NDArray[Any]
    expectation_errors: npt.NDArray[Any]
    measurement_order: npt.NDArray[Any]
    point_estimates: dict[str, npt.NDArray[Any]]
    fit_parameters: dict[str, npt.NDArray[Any]]
    fit_parameter_errors: dict[str, npt.NDArray[Any]]
    derived_values: dict[str, npt.NDArray[Any]]
    fit_success: npt.NDArray[Any]
    fit_messages: tuple[str, ...]
    t1_plot_mask: npt.NDArray[Any]
    t2_plot_mask: npt.NDArray[Any]
    t1_exclusion_messages: tuple[str | None, ...]
    t2_exclusion_messages: tuple[str | None, ...]
    min_a0: float | None
    min_b0: float | None
    uncertainty_method: str


@dataclass(frozen=True)
class _SpinLockRunPayload:
    """Qubex result plus the requested and hardware-feasible sweep ranges."""

    result: Any
    requested_frequencies: np.ndarray
    accepted_frequencies: np.ndarray
    rejected_frequencies: np.ndarray


class CheckSpinLockSpectroscopy(QubexTask):
    """Measure T1-rho and T2-rho over a hardware-feasible Rabi-frequency sweep."""

    name: str = "CheckSpinLockSpectroscopy"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        **required_rabi_normalization_inputs(),
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated GE control frequency",
        ),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated readout frequency",
        ),
        "readout_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            less_than_or_equal=1,
            description="Calibrated readout amplitude",
        ),
        "hpi_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            description="Calibrated half-pi pulse amplitude",
        ),
        "hpi_duration": InputParameterSpec.required_database(
            unit="ns",
            greater_than=0,
            description="Calibrated half-pi pulse duration",
        ),
        "t1": InputParameterSpec.database_or_default(
            default=0,
            unit="μs",
            greater_than_or_equal=0,
            description="T1 used to derive the duration sweep; zero means unavailable",
        ),
        "t2_echo": InputParameterSpec.database_or_default(
            default=0,
            unit="μs",
            greater_than_or_equal=0,
            description="T2 echo used to derive the duration sweep; zero means unavailable",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "spin_lock_frequency_range": RunParameterSpec(
            unit="GHz",
            value_type="np.linspace",
            default=(0.004, 0.1, 25),
            description="Requested spin-lock Rabi-frequency sweep",
        ),
        "duration_range": RunParameterSpec(
            unit="ns",
            value_type="list",
            default=None,
            description=(
                "Explicit flat-top duration sweep. When unset, derive it from QDash T1/T2 "
                "echo values or use 100 ns to 200 μs when both are unavailable."
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Shots per expectation value",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {}

    def _requested_frequencies(self) -> np.ndarray:
        frequencies = np.asarray(
            self.run_parameters["spin_lock_frequency_range"].get_value(), dtype=float
        )
        if frequencies.ndim != 1 or frequencies.size == 0:
            raise ValueError("spin_lock_frequency_range must be a non-empty 1D array")
        if not np.isfinite(frequencies).all() or np.any(frequencies <= 0):
            raise ValueError("spin_lock_frequency_range must contain positive finite values")
        return frequencies

    @staticmethod
    def _filter_reachable_frequencies(
        exp: Any, target: str, requested: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        reachable: list[float] = []
        rejected: list[float] = []
        for frequency in requested:
            try:
                amplitude = float(exp.pulse.calc_control_amplitude(target, float(frequency)))
                actual_frequency = float(exp.pulse.calc_rabi_rate(target, amplitude))
            except (ArithmeticError, RuntimeError, ValueError):
                rejected.append(float(frequency))
                continue
            if (
                np.isfinite(amplitude)
                and abs(amplitude) <= 1
                and np.isfinite(actual_frequency)
                and actual_frequency > 0
            ):
                reachable.append(float(frequency))
            else:
                rejected.append(float(frequency))
        if not reachable:
            raise ValueError(
                "No requested spin-lock frequency is reachable with the calibrated Rabi model."
            )
        return np.asarray(reachable), np.asarray(rejected)

    def _duration_inputs(self) -> tuple[np.ndarray | None, float | None, float | None]:
        duration_parameter = self.run_parameters["duration_range"]
        if duration_parameter.value is not None:
            return np.asarray(duration_parameter.get_value(), dtype=float), None, None

        t1_us = self._get_calibration_value("t1")
        t2_echo_us = self._get_calibration_value("t2_echo")
        t1_ns = 1000.0 * t1_us if t1_us > 0 else None
        t2_echo_ns = 1000.0 * t2_echo_us if t2_echo_us > 0 else None
        if t1_ns is None and t2_echo_ns is None:
            return DEFAULT_DURATION_RANGE.copy(), None, None
        return None, t1_ns, t2_echo_ns

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the spectroscopy sweep after removing unreachable drive points."""
        from qubex.contrib import spin_lock_relaxation_spectroscopy

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        resonator_label = self.get_resonator_label(backend, qid)

        # ``calc_control_amplitude`` derives the spin-lock drive from both the
        # restored Rabi fit and Qubex's current reference control amplitude.
        # Keep that reference aligned with the QDash calibration snapshot.
        exp.params.control_amplitude[label] = self._get_calibration_value("control_amplitude")
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")

        requested = self._requested_frequencies()
        accepted, rejected = self._filter_reachable_frequencies(exp, label, requested)
        if rejected.size:
            logger.warning(
                "Excluding unreachable spin-lock frequencies for %s: %s GHz",
                label,
                rejected.tolist(),
            )
        duration_range, t1_ns, t2_echo_ns = self._duration_inputs()

        with exp.modified_frequencies(
            {
                label: self._get_calibration_value("control_frequency"),
                resonator_label: self._get_calibration_value("readout_frequency"),
            }
        ):
            result = spin_lock_relaxation_spectroscopy(
                exp,
                targets=[label],
                spin_lock_frequency_range=accepted,
                duration_range=duration_range,
                t1=t1_ns,
                t2_echo=t2_echo_ns,
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                plot=False,
                save_image=False,
            )
        return RunResult(
            raw_result=_SpinLockRunPayload(
                result=result,
                requested_frequencies=requested,
                accepted_frequencies=accepted,
                rejected_frequencies=rejected,
            )
        )

    @staticmethod
    def _target_result(payload: _SpinLockRunPayload) -> tuple[str, Mapping[str, Any]]:
        results = payload.result.data.get("results")
        if not isinstance(results, dict) or len(results) != 1:
            raise ValueError("Spin-lock result must contain exactly one target")
        target, data = next(iter(results.items()))
        if not isinstance(data, dict):
            raise TypeError("Spin-lock target result must be a mapping")
        return str(target), data

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Build one structured NetCDF artifact containing reanalysis inputs and fits."""
        payload = run_result.raw_result
        if not isinstance(payload, _SpinLockRunPayload):
            # This also accepts lightweight test/re-execution payloads with the same fields.
            required = (
                "result",
                "requested_frequencies",
                "accepted_frequencies",
                "rejected_frequencies",
            )
            if not all(hasattr(payload, name) for name in required):
                raise TypeError("Unsupported spin-lock run payload")
        target, data = self._target_result(payload)
        fit_parameter_names = ("theta", "t1_rho", "t2_rho", "p_inf", "a0", "b0")
        derived_names = ("shift", "axis_rotation_frequency")
        artifact = SpinLockSpectroscopyData(
            target=target,
            requested_rabi_frequencies=np.asarray(payload.requested_frequencies),
            accepted_rabi_frequencies=np.asarray(payload.accepted_frequencies),
            rejected_rabi_frequencies=np.asarray(payload.rejected_frequencies),
            duration_range=np.asarray(data["duration_range"]),
            total_pulse_duration_range=np.asarray(data["total_pulse_duration_range"]),
            ramp_duration=float(data["ramp_duration"]),
            drive_amplitudes=np.asarray(data["drive_amplitudes"]),
            rabi_frequencies=np.asarray(data["rabi_frequencies"]),
            expectation_labels=tuple(data["expectation_labels"]),
            mean_iq=np.asarray(data["mean_iq"]),
            expectations=np.asarray(data["expectations"]),
            expectation_errors=np.asarray(data["expectation_errors"]),
            measurement_order=np.asarray(data["measurement_order"]),
            point_estimates={
                name: np.asarray(values) for name, values in data["point_estimates"].items()
            },
            fit_parameters={name: np.asarray(data[name]) for name in fit_parameter_names},
            fit_parameter_errors={
                name: np.asarray(data[f"{name}_error"]) for name in fit_parameter_names
            },
            derived_values={
                name: np.asarray(data[name])
                for name in (*derived_names, *(f"{name}_error" for name in derived_names))
            },
            fit_success=np.asarray(data["fit_success"], dtype=bool),
            fit_messages=tuple(str(message) for message in data["fit_messages"]),
            t1_plot_mask=np.asarray(data["t1_plot_mask"], dtype=bool),
            t2_plot_mask=np.asarray(data["t2_plot_mask"], dtype=bool),
            t1_exclusion_messages=tuple(data["t1_exclusion_messages"]),
            t2_exclusion_messages=tuple(data["t2_exclusion_messages"]),
            min_a0=data["min_a0"],
            min_b0=data["min_b0"],
            uncertainty_method=str(data["uncertainty_method"]),
        )
        return [artifact]

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Persist both figures and fail only when every frequency fit failed."""
        del execution_id
        payload = run_result.raw_result
        label, data = self._target_result(payload)
        figures_by_name = payload.result.figures or {}
        figures: list[go.Figure] = [
            figure
            for name in (
                f"{label}_parameter_heatmaps",
                f"{label}_relaxation_spectroscopy",
            )
            if (figure := figures_by_name.get(name)) is not None
        ]
        fit_success = np.asarray(data["fit_success"], dtype=bool)
        validation_error = None
        if not np.any(fit_success):
            validation_error = f"Spin-lock relaxation fit failed at all frequencies for {label}."
        return PostProcessResult(
            output_parameters={},
            figures=figures,
            validation_error=validation_error,
        )
