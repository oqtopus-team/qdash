"""Measure the FH transition frequency with Qubex adaptive chevron analysis."""

import math
from typing import ClassVar

from qubex.contrib.experiment import estimate_fh_frequency_from_chevron_adaptive
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.calibtasks.qubex.validation import (
    finite_value_error,
    first_validation_error,
    require_fh_configuration,
)
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckAdaptiveFHChevron(QubexTask):
    """Adaptively measure the FH transition using stored Qubex GE and EF pulses.

    The recorded HPI and EF pi inputs enforce the calibration prerequisites. Qubex resolves the
    actual preparation waveforms from the synchronized session when it constructs each sequence.
    """

    name: str = "CheckAdaptiveFHChevron"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "control_frequency_ef": InputParameterSpec.required_database(
            fallback_parameter_names=("ef_frequency",), unit="GHz"
        ),
        "control_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_duration": InputParameterSpec.required_database(unit="ns"),
        "ef_pi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "ef_pi_duration": InputParameterSpec.required_database(unit="ns"),
        "readout_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",), unit="GHz"
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "detuning_range": RunParameterSpec(
            unit="GHz",
            value_type="np.linspace",
            default=(-0.05, 0.05, 41),
            description="Final FH detuning sweep around the adaptively estimated frequency",
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="range",
            default=(0, 257, 8),
            description="Final FH drive duration sweep",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS // 4,
            description="Number of shots per FH chevron point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
        "minimum_peak_background_rms_ratio": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=5.0,
            description="Minimum matched-transform peak/background RMS ratio",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "fh_frequency": OutputParameterSpec(
            unit="GHz",
            description="Measured f-to-h transition frequency",
            publish_targets=("fh_frequency", "control_frequency_fh"),
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        label = exp.ctx.resolve_fh_label(self.get_qubit_label(backend, qid))
        result = run_result.raw_result
        frequency = result.data["resonant_frequencies"].get(label)
        ef_frequency = self._get_calibration_value("control_frequency_ef")
        threshold = self.run_parameters["minimum_peak_background_rms_ratio"].get_value()
        threshold_error = finite_value_error(
            threshold, "minimum_peak_background_rms_ratio", minimum=0
        )
        self.output_parameters["fh_frequency"].value = frequency
        final_keys = (f"{label}_measurement", f"{label}_transform")
        figures = [result.figures[key] for key in final_keys if key in result.figures]
        figures.extend(figure for key, figure in result.figures.items() if key not in final_keys)
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=figures,
            validation_error=first_validation_error(
                finite_value_error(frequency, "fh_frequency", minimum=0, maximum=ef_frequency),
                threshold_error,
                finite_value_error(
                    result.data["peak_background_rms_ratios"].get(label),
                    "FH chevron peak/background RMS ratio",
                    minimum=threshold if threshold_error is None else None,
                ),
            ),
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        require_fh_configuration(exp, label)
        control_amplitude = self._get_calibration_value("control_amplitude")
        exp.params.control_amplitude[label] = control_amplitude
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        ge_frequency = self._get_calibration_value("control_frequency")
        ef_frequency = self._get_calibration_value("control_frequency_ef")
        configured_fh_frequency = exp.quantum_system.get_qubit(label).control_frequency_fh_value
        if configured_fh_frequency is not None and math.isfinite(configured_fh_frequency):
            fh_frequency = float(configured_fh_frequency)
        else:
            fh_frequency = 2 * ef_frequency - ge_frequency
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): ge_frequency,
                exp.ctx.resolve_ef_label(label): ef_frequency,
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = estimate_fh_frequency_from_chevron_adaptive(
                exp=exp,
                targets=[label],
                frequencies={label: fh_frequency},
                amplitudes={label: control_amplitude / math.sqrt(3)},
                final_detuning_range=self.run_parameters["detuning_range"].get_value(),
                final_time_range=self.run_parameters["time_range"].get_value(),
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                plot=False,
                save_image=False,
            )
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        raise NotImplementedError(f"{self.name} does not support batch execution")
