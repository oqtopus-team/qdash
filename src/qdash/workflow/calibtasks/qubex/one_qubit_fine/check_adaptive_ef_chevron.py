"""Measure EF frequency and anharmonicity with Qubex adaptive chevron analysis."""

import math
from typing import ClassVar

from qubex.contrib.experiment import estimate_ef_frequency_from_chevron_adaptive
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
)
from qdash.workflow.calibtasks.qubex.validation import (
    finite_value_error,
    first_validation_error,
    require_ef_configuration,
)
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckAdaptiveEFChevron(QubexTask):
    """Adaptively measure f_ef and alpha = f_ef - f_ge using a stored Qubex GE pulse.

    The recorded HPI inputs enforce the calibration prerequisite. Qubex resolves the actual
    preparation waveform from the synchronized session when it constructs each sequence.
    """

    name: str = "CheckAdaptiveEFChevron"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "control_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            description="Calibrated GE amplitude used to derive the initial EF drive amplitude",
        ),
        "hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_duration": InputParameterSpec.required_database(unit="ns"),
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
            description="Final EF detuning sweep around the adaptively estimated frequency",
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="range",
            default=(0, 257, 8),
            description="Final EF drive duration sweep",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS // 4,
            description="Number of shots per EF chevron point",
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
        "ef_frequency": OutputParameterSpec(
            unit="GHz",
            description="Measured e-to-f transition frequency",
            publish_targets=(
                "ef_frequency",
                "control_frequency_ef",
            ),
        ),
        "qubit_anharmonicity": OutputParameterSpec(
            unit="GHz", description="Anharmonicity alpha = ef_frequency - control_frequency"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        label = exp.ctx.resolve_ef_label(self.get_qubit_label(backend, qid))
        result = run_result.raw_result
        frequency = result.data["resonant_frequencies"].get(label)
        ge_frequency = self._get_calibration_value("control_frequency")
        anharmonicity = None if frequency is None else frequency - ge_frequency
        threshold = self.run_parameters["minimum_peak_background_rms_ratio"].get_value()
        threshold_error = finite_value_error(
            threshold, "minimum_peak_background_rms_ratio", minimum=0
        )
        self.output_parameters["ef_frequency"].value = frequency
        self.output_parameters["qubit_anharmonicity"].value = anharmonicity
        # Keep the final chevron and its transform together at the front.
        final_keys = (f"{label}_measurement", f"{label}_transform")
        figures = [result.figures[key] for key in final_keys if key in result.figures]
        figures.extend(figure for key, figure in result.figures.items() if key not in final_keys)
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=figures,
            validation_error=first_validation_error(
                finite_value_error(frequency, "ef_frequency", minimum=0),
                finite_value_error(anharmonicity, "qubit_anharmonicity", maximum=0),
                threshold_error,
                finite_value_error(
                    result.data["peak_background_rms_ratios"].get(label),
                    "EF chevron peak/background RMS ratio",
                    minimum=threshold if threshold_error is None else None,
                ),
            ),
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        require_ef_configuration(exp, label)
        control_amplitude = self._get_calibration_value("control_amplitude")
        exp.params.control_amplitude[label] = control_amplitude
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        ge_frequency = self._get_calibration_value("control_frequency")
        configured_ef_frequency = exp.quantum_system.get_qubit(label).control_frequency_ef_value
        if configured_ef_frequency is not None and math.isfinite(configured_ef_frequency):
            ef_frequency = float(configured_ef_frequency)
        else:
            # Match Qubex's missing-anharmonicity default (E_J / E_C = 50)
            # without allowing a persisted spectroscopy estimate to affect the seed.
            ef_frequency = ge_frequency * 18 / 19
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): ge_frequency,
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = estimate_ef_frequency_from_chevron_adaptive(
                exp=exp,
                targets=[label],
                frequencies={label: ef_frequency},
                amplitudes={label: control_amplitude / math.sqrt(2)},
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
