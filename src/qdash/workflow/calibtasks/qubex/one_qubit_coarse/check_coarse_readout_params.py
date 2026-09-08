import math
from typing import Any, ClassVar

import numpy as np
from numpy.typing import NDArray
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.calibtasks.qubex.validation import (
    DEFAULT_RABI_R2_THRESHOLD,
    finite_value_error,
    first_validation_error,
)
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.engine.progress import ProgressPlan


class _ReadoutSweepExperiment:
    """Forward the resolved duration through the Qubex contrib Rabi sweep."""

    def __init__(self, experiment: Any, readout_duration: float) -> None:
        self.ctx = experiment.ctx
        self._experiment = experiment
        self._readout_duration = readout_duration

    def rabi_experiment(self, **kwargs: Any) -> Any:
        return self._experiment.rabi_experiment(readout_duration=self._readout_duration, **kwargs)


def _selected_rabi_r2(result: Any, label: str) -> float | None:
    """Read the stored R² for the selected frequency/amplitude, without refitting."""
    data = result.data
    try:
        frequencies = np.asarray(data["frequency_range"], dtype=float)
        amplitudes = np.asarray(data["readout_amplitudes"], dtype=float)
        if frequencies.ndim != 1 or amplitudes.ndim != 1:
            return None
        frequency_indices = np.flatnonzero(frequencies == data["optimal_readout_frequency"])
        amplitude_indices = np.flatnonzero(amplitudes == data["optimal_readout_amplitude"])
        if frequency_indices.size != 1 or amplitude_indices.size != 1:
            return None

        # Qubex scans amplitudes in the outer loop and frequencies in the inner loop.
        rabi_results = data["rabi_results"]
        if len(rabi_results) != amplitudes.size * frequencies.size:
            return None
        index = int(amplitude_indices[0]) * frequencies.size + int(frequency_indices[0])
        rabi_params = rabi_results[index].rabi_params
        if rabi_params is None:
            return None
        r2 = float(rabi_params[label].r2)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None
    return r2 if math.isfinite(r2) else None


class CheckCoarseReadoutParams(QubexTask):
    """Task to check the Optimal Readout Frequency"""

    name: str = "CheckCoarseReadoutParams"
    task_type: str = "qubit"
    r2_threshold: float = DEFAULT_RABI_R2_THRESHOLD
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qubit_frequency": InputParameterSpec.required_database(
            unit="GHz", greater_than=0, description="Qubit drive frequency for the Rabi sweep"
        ),
        "control_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            less_than=1,
            description="Control pulse amplitude for the Rabi sweep",
        ),
        "readout_frequency": InputParameterSpec.required_database(
            unit="GHz", greater_than=0, description="Center frequency of the readout sweep"
        ),
        "readout_amplitude": InputParameterSpec.required_database(
            unit="a.u.", greater_than=0, description="Reference amplitude of the readout sweep"
        ),
        "readout_duration": InputParameterSpec.database_or_default(
            default=DEFAULT_READOUT_DURATION,
            unit="ns",
            greater_than=0,
            description="Readout pulse duration for reference and Rabi measurements",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "detuning_range": RunParameterSpec(
            unit="GHz",
            value_type="np.linspace",
            default=(-0.015, 0.015, 13),
            description="Offsets from readout_frequency (start, stop, number of points)",
        ),
        "readout_amplitude_ratio_range": RunParameterSpec(
            unit="",
            value_type="np.linspace",
            default=(0.8, 1.2, 5),
            description=(
                "Multipliers of readout_amplitude (start, stop, number of points). "
                "Sweep amplitudes are capped at 1 and duplicate points are removed."
            ),
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="np.arange",
            default=(0, 101, 4),
            description="Rabi drive durations at each readout point (start, stop, step)",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS // 2,
            description="Number of shots per Rabi drive duration at each readout point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "readout_frequency": OutputParameterSpec(
            unit="GHz", description="Optimal Readout Frequency"
        ),
        "readout_amplitude": OutputParameterSpec(
            unit="a.u.", description="Optimal Readout Amplitude"
        ),
    }

    def _readout_sweep(self) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        frequency = self._get_calibration_value("readout_frequency")
        amplitude = self._get_calibration_value("readout_amplitude")
        if not math.isfinite(frequency) or frequency <= 0:
            raise ValueError("readout_frequency must be finite and positive")
        if not math.isfinite(amplitude) or not 0 < amplitude <= 1:
            raise ValueError("readout_amplitude must be finite and within (0, 1]")

        detunings = np.asarray(self.run_parameters["detuning_range"].get_value(), dtype=float)
        ratios = np.asarray(
            self.run_parameters["readout_amplitude_ratio_range"].get_value(), dtype=float
        )
        if detunings.ndim != 1 or detunings.size == 0 or not np.isfinite(detunings).all():
            raise ValueError("detuning_range must contain finite frequency offsets")
        if (
            ratios.ndim != 1
            or ratios.size == 0
            or not np.isfinite(ratios).all()
            or np.any(ratios <= 0)
        ):
            raise ValueError("readout_amplitude_ratio_range must contain finite positive ratios")
        frequencies = np.unique(frequency + detunings)
        if not np.isfinite(frequencies).all() or np.any(frequencies <= 0):
            raise ValueError("Readout sweep frequencies must be finite and positive")
        amplitudes = np.unique(np.minimum(amplitude * ratios, 1.0))
        return frequencies, amplitudes

    def get_progress_plan(self) -> ProgressPlan:
        """Count one Rabi sweep per effective readout frequency/amplitude pair."""
        frequencies, amplitudes = self._readout_sweep()
        n_sweeps = int(frequencies.size * amplitudes.size)
        return ProgressPlan(n_sweeps, n_sweeps)

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result
        self.output_parameters["readout_frequency"].value = result.data["optimal_readout_frequency"]
        self.output_parameters["readout_amplitude"].value = result.data["optimal_readout_amplitude"]
        output_parameters = self.attach_execution_id(execution_id)
        fig = result.figure
        figures = [fig]
        selected_r2 = run_result.r2.get(qid) if run_result.r2 is not None else None
        validation_error = first_validation_error(
            finite_value_error(selected_r2, "Selected readout point R²", maximum=1.0),
            finite_value_error(result.data["optimal_readout_frequency"], "readout_frequency"),
            finite_value_error(result.data["optimal_readout_amplitude"], "readout_amplitude"),
        )
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            validation_error=validation_error,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        import qubex

        frequencies, amplitudes = self._readout_sweep()
        readout_duration = self._get_calibration_value("readout_duration")
        if not math.isfinite(readout_duration) or readout_duration <= 0:
            raise ValueError("readout_duration must be finite and positive")
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)

        # The contrib helper reads drive settings from ctx and has no duration argument.
        # Keep temporary drive overrides scoped to this sweep; forward duration to Rabi.
        sweep_exp: Any = _ReadoutSweepExperiment(exp, readout_duration)
        with self._apply_parameter_overrides(backend, qid):
            result = qubex.contrib.characterize_coarse_readout_parameters(
                sweep_exp,
                target=label,
                frequency_range=frequencies,
                readout_amplitudes=amplitudes,
                time_range=self.run_parameters["time_range"].get_value(),
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
            )

        r2 = _selected_rabi_r2(result, label)
        if r2 is not None and r2 <= 1.0 and not self.r2_is_lower_than_threshold(r2):
            self.save_calibration(backend)
        return RunResult(raw_result=result, r2={qid: r2})
