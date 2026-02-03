from typing import ClassVar

import numpy as np
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.measurement.measurement import DEFAULT_READOUT_DURATION

DEFAULT_SNR_THRESHOLD = 1.0


class ChevronPattern(QubexTask):
    """Task to check the chevron pattern."""

    name: str = "ChevronPattern"
    task_type: str = "qubit"
    timeout: int = 60 * 240
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,
        "readout_amplitude": None,
        "readout_frequency": None,
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "control_amplitude": RunParameterModel(
            unit="a.u.", value_type="float", value=0.0125, description="Control pulse amplitude"
        ),
        "readout_amplitude_range": RunParameterModel(
            unit="a.u.",
            value_type="np.linspace",
            value=(0.0, 0.2, 51),
            description="Amplitude range for readout sweep",
        ),
        "snr_threshold": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=DEFAULT_SNR_THRESHOLD,
            description="SNR threshold for determining readout amplitude",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(unit="GHz", description="Qubit bare frequency"),
        "readout_amplitude": ParameterModel(
            unit="a.u.", description="Optimal readout amplitude from SNR threshold"
        ),
    }

    def preprocess(self, backend: QubexBackend, qid: str) -> PreProcessResult:
        """Preprocess: load params from DB, then sweep readout amplitude to determine optimal value."""
        result = super().preprocess(backend, qid)
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        amplitude_range = self.run_parameters["readout_amplitude_range"].get_value()
        threshold = self.run_parameters["snr_threshold"].get_value()

        sweep_result = exp.sweep_readout_amplitude(
            targets=[label],
            amplitude_range=amplitude_range,
        )
        snr = np.asarray(sweep_result["snr"][label])
        idx = np.where(snr > threshold)[0]
        if len(idx) > 0:
            i = idx[0]
            if i > 0:
                x1, x2 = amplitude_range[i - 1], amplitude_range[i]
                y1, y2 = snr[i - 1], snr[i]
                optimal_amp = float(x1 + (threshold - y1) * (x2 - x1) / (y2 - y1))
            else:
                optimal_amp = float(amplitude_range[i])
            readout_amp_param = self.input_parameters["readout_amplitude"]
            assert readout_amp_param is not None
            readout_amp_param.value = optimal_amp
            self.output_parameters["readout_amplitude"].value = optimal_amp
            print(f"readout_amplitude={optimal_amp:.6f} (from SNR sweep, threshold={threshold})")
        else:
            print(f"WARNING: SNR never exceeded {threshold} for {label}, using DB value")

        return result

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["qubit_frequency"].value = result["resonant_frequencies"][label]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result["fig"][label]]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]

        readout_amplitude = self.input_parameters["readout_amplitude"]
        readout_frequency = self.input_parameters["readout_frequency"]
        qubit_frequency = self.input_parameters["qubit_frequency"]
        assert readout_amplitude is not None
        assert readout_frequency is not None
        assert qubit_frequency is not None

        exp.params.readout_amplitude[labels[0]] = readout_amplitude.value
        with exp.modified_frequencies(
            {"R" + labels[0]: readout_frequency.value}
        ):
            result = exp.chevron_pattern(
                amplitudes={labels[0]: self.run_parameters["control_amplitude"].value},
                frequencies={labels[0]: qubit_frequency.value},
                targets=labels,
                detuning_range=np.linspace(-0.05, 0.05, 51),
                time_range=np.arange(0, 201, 4),
            )

        self.save_calibration(backend)
        return RunResult(raw_result=result)
