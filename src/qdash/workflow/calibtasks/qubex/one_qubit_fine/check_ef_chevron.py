"""Measure EF frequency and anharmonicity with Qubex chevron analysis."""

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
from qdash.workflow.calibtasks.qubex.validation import finite_value_error, first_validation_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckEFChevron(QubexTask):
    """Measure f_ef and alpha = f_ef - f_ge using the calibrated GE DRAG pi pulse."""

    name: str = "CheckEFChevron"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "qubit_frequency": InputParameterSpec.required_database(unit="GHz"),
        "anharmonicity": InputParameterSpec.database_or_default(
            default=-0.3, unit="GHz", description="Initial EF frequency offset from f_ge"
        ),
        "ef_control_amplitude": InputParameterSpec.database_or_default(
            default=0.0625, unit="a.u.", description="EF drive pulse amplitude"
        ),
        "drag_pi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "drag_pi_duration": InputParameterSpec.required_database(
            parameter_aliases=("drag_pi_length",), unit="ns"
        ),
        "drag_pi_beta": InputParameterSpec.required_database(),
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
            unit="GHz", description="Measured e-to-f transition frequency"
        ),
        "anharmonicity": OutputParameterSpec(
            unit="GHz", description="Anharmonicity alpha = ef_frequency - qubit_frequency"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(backend)
        label = exp.ctx.resolve_ef_label(self.get_qubit_label(backend, qid))
        result = run_result.raw_result
        frequency = result.data["resonant_frequencies"].get(label)
        ge_frequency = self._get_calibration_value("qubit_frequency")
        anharmonicity = None if frequency is None else frequency - ge_frequency
        threshold = self.run_parameters["minimum_peak_background_rms_ratio"].get_value()
        threshold_error = finite_value_error(
            threshold, "minimum_peak_background_rms_ratio", minimum=0
        )
        self.output_parameters["ef_frequency"].value = frequency
        self.output_parameters["anharmonicity"].value = anharmonicity
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=list(result.figures.values()),
            validation_error=first_validation_error(
                finite_value_error(frequency, "ef_frequency", minimum=0),
                finite_value_error(anharmonicity, "anharmonicity", maximum=0),
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
        readout_amp_param = self.input_parameters["readout_amplitude"]
        if readout_amp_param is not None:
            exp.params.readout_amplitude[label] = readout_amp_param.value
        ef_frequency = self._get_calibration_value("qubit_frequency") + self._get_calibration_value(
            "anharmonicity"
        )
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): self._get_calibration_value("control_frequency"),
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = estimate_ef_frequency_from_chevron_adaptive(
                exp=exp,
                targets=[label],
                frequencies={label: ef_frequency},
                amplitudes={label: self._get_calibration_value("ef_control_amplitude")},
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
