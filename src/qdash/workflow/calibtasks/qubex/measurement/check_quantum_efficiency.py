"""Quantum-efficiency measurement task."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
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
from qdash.workflow.calibtasks.qubex.validation import finite_value_error

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend

logger = logging.getLogger(__name__)


class QuantumEfficiencyData(DataModel):
    """NetCDF artifact containing the compact numerical measurement result."""

    target: str
    readout_amplitudes: npt.NDArray[Any]
    quantum_efficiency: float
    quantum_efficiency_error: float
    pointwise_quantum_efficiency: npt.NDArray[Any]
    projection_method: str
    projection_weights: npt.NDArray[Any] | None
    projection_reference_amplitude: float | None
    snr_values: npt.NDArray[Any]
    snr_standard_errors: npt.NDArray[Any]
    snr_uncertainty_methods: tuple[str, ...]
    snr_signal: npt.NDArray[Any]
    snr_noise: npt.NDArray[Any]
    snr_slope: float
    snr_slope_error: float
    snr_fit_amplitudes: npt.NDArray[Any]
    snr_fit_values: npt.NDArray[Any]
    rho01: npt.NDArray[Any]
    rho01_standard_errors: npt.NDArray[Any]
    beta_m_raw: npt.NDArray[Any]
    dephasing_prefactor: float
    dephasing_prefactor_error: float
    sigma_m: float
    sigma_m_error: float
    dephasing_fit_amplitudes: npt.NDArray[Any]
    dephasing_fit_values: npt.NDArray[Any]
    early_stop_enabled: bool
    early_stopped: bool


class CheckQuantumEfficiency(QubexTask):
    """Measure the readout-chain quantum efficiency of one qubit."""

    name: str = "CheckQuantumEfficiency"
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
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "amplitude_range": RunParameterSpec(
            unit="a.u.",
            value_type="list",
            default=None,
            description=(
                "Readout-amplitude sweep. Uses Qubex's target-specific geometric default "
                "when unset."
            ),
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Shots per Ramsey phase and readout-state measurement",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "quantum_efficiency": OutputParameterSpec(
            unit="a.u.",
            description="Fit-based readout-chain quantum efficiency",
        ),
    }

    def _amplitude_range(self) -> np.ndarray | None:
        parameter = self.run_parameters["amplitude_range"]
        if parameter.value is None:
            return None
        amplitudes = np.asarray(parameter.get_value(), dtype=float)
        if amplitudes.ndim != 1 or amplitudes.size < 2:
            raise ValueError("amplitude_range must be a 1D array with at least two values")
        if not np.isfinite(amplitudes).all() or np.any(amplitudes < 0):
            raise ValueError("amplitude_range must contain finite nonnegative values")
        if np.any(np.diff(amplitudes) <= 0):
            raise ValueError("amplitude_range must be strictly increasing")
        return amplitudes

    def _run_kwargs(self) -> dict[str, Any]:
        shots = int(self.run_parameters["shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        readout_duration = float(self.run_parameters["readout_duration"].get_value())
        if shots <= 0:
            raise ValueError("shots must be positive")
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        if not math.isfinite(readout_duration) or readout_duration <= 0:
            raise ValueError("readout_duration must be finite and positive")
        return {
            "amplitude_range": self._amplitude_range(),
            "n_shots": shots,
            "shot_interval": interval,
            "readout_duration": readout_duration,
            "plot": False,
            "save_image": False,
        }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run Qubex quantum-efficiency measurement with calibrated context."""
        from qubex.contrib import quantum_efficiency_measurement

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        resonator_label = self.get_resonator_label(backend, qid)
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        with exp.modified_frequencies(
            {
                label: self._get_calibration_value("control_frequency"),
                resonator_label: self._get_calibration_value("readout_frequency"),
            }
        ):
            result = quantum_efficiency_measurement(
                exp,
                targets=label,
                **self._run_kwargs(),
            )
        return RunResult(raw_result=result)

    @staticmethod
    def _mapping(value: Any, name: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError(f"Quantum-efficiency result field {name!r} must be a mapping")
        return value

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Build a compact NetCDF artifact from stable numerical result fields."""
        data = self._mapping(run_result.raw_result.data, "data")
        snr = self._mapping(data["snr"], "snr")
        dephasing = self._mapping(
            data["measurement_induced_dephasing"],
            "measurement_induced_dephasing",
        )
        snr_fit = self._mapping(data["snr_fit"], "snr_fit")
        dephasing_fit = self._mapping(
            data["measurement_induced_dephasing_fit"],
            "measurement_induced_dephasing_fit",
        )
        projection_weights = data.get("projection_weights")
        artifact = QuantumEfficiencyData(
            target=str(data["target"]),
            readout_amplitudes=np.asarray(data["readout_amplitudes"]),
            quantum_efficiency=float(data["quantum_efficiency"]),
            quantum_efficiency_error=float(data["quantum_efficiency_error"]),
            pointwise_quantum_efficiency=np.asarray(data["pointwise_quantum_efficiency"]),
            projection_method=str(data["projection_method"]),
            projection_weights=(
                None if projection_weights is None else np.asarray(projection_weights)
            ),
            projection_reference_amplitude=(
                None
                if data.get("projection_reference_amplitude") is None
                else float(data["projection_reference_amplitude"])
            ),
            snr_values=np.asarray(snr["values"]),
            snr_standard_errors=np.asarray(snr["standard_error"]),
            snr_uncertainty_methods=tuple(str(item) for item in snr["uncertainty_method"]),
            snr_signal=np.asarray(snr["signal"]),
            snr_noise=np.asarray(snr["noise"]),
            snr_slope=float(snr_fit["a"]),
            snr_slope_error=float(snr_fit["a_err"]),
            snr_fit_amplitudes=np.asarray(snr_fit["fit_amplitudes"]),
            snr_fit_values=np.asarray(snr_fit["y_fit"]),
            rho01=np.asarray(dephasing["rho01"]),
            rho01_standard_errors=np.asarray(dephasing["rho01_standard_error"]),
            beta_m_raw=np.asarray(dephasing["beta_m_raw"]),
            dephasing_prefactor=float(dephasing_fit["b"]),
            dephasing_prefactor_error=float(dephasing_fit["b_err"]),
            sigma_m=float(dephasing_fit["sigma_m"]),
            sigma_m_error=float(dephasing_fit["sigma_m_err"]),
            dephasing_fit_amplitudes=np.asarray(dephasing_fit["fit_amplitudes"]),
            dephasing_fit_values=np.asarray(dephasing_fit["rho01_fit"]),
            early_stop_enabled=bool(data.get("early_stop_enabled", False)),
            early_stopped=bool(data.get("early_stopped", False)),
        )
        return [artifact]

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Publish the efficiency, retain values above one, and expose only overview."""
        del backend, qid
        result = run_result.raw_result
        efficiency = float(result.data["quantum_efficiency"])
        self.output_parameters["quantum_efficiency"].value = efficiency
        if math.isfinite(efficiency) and efficiency > 1:
            logger.warning(
                "Measured quantum efficiency exceeds the physical bound: %s",
                efficiency,
            )
        figures_by_name = result.figures or {}
        overview = figures_by_name.get("overview")
        if overview is None:
            overview = result.figure
        figures = [] if overview is None else [overview]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=figures,
            validation_error=finite_value_error(
                efficiency,
                "quantum efficiency",
                minimum=0.0,
            ),
        )
