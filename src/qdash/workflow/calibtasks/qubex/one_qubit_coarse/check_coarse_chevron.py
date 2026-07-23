import math
from typing import ClassVar

import numpy as np
import plotly.graph_objects as go
from qubex.measurement.measurement_defaults import DEFAULT_READOUT_DURATION

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_READOUT_AMPLITUDE = 0.2
DEFAULT_CONTROL_AMPLITUDE = 0.0625
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0


class CheckCoarseChevron(QubexTask):
    """Coarse chevron pattern that locates the qubit resonance with a wide, sparse sweep.

    Designed to bracket spectroscopy seeds that may be off by up to ~60 MHz, so the
    downstream CheckFineChevron can use a narrow ±10 MHz window for the fine measurement.
    """

    name: str = "CheckCoarseChevron"
    task_type: str = "qubit"
    timeout: int = 60 * 240
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        # Coarse f01 from CheckQubitSpectroscopy (refined by CheckControlAmplitude
        # if it ran). The chevron's wide ±75 MHz sweep is centered on this; the
        # task then writes back the proper qubit_frequency from fit_detuned_rabi.
        "coarse_qubit_frequency": None,
        "readout_frequency": None,
        "readout_amplitude": None,
        "control_amplitude": ParameterModel(
            value=DEFAULT_CONTROL_AMPLITUDE, unit="a.u.", description="Control pulse amplitude"
        ),
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "readout_amplitude": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=DEFAULT_READOUT_AMPLITUDE,
            description="Readout amplitude",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(unit="GHz", description="Qubit bare frequency (coarse)"),
        "control_amplitude": ParameterModel(
            unit="a.u.", description="Control pulse amplitude used for coarse chevron"
        ),
        "readout_amplitude": ParameterModel(
            unit="a.u.", description="Readout amplitude used for coarse chevron"
        ),
    }

    def preprocess(self, backend: QubexBackend, qid: str) -> PreProcessResult:
        """Preprocess: load params from DB and validate control_amplitude."""
        result = super().preprocess(backend, qid)

        param = self.input_parameters.get("control_amplitude")
        value = param.value if param is not None else None
        if (
            value is None
            or not isinstance(value, (int, float))
            or math.isnan(value)
            or value <= CONTROL_AMPLITUDE_MIN
            or value >= CONTROL_AMPLITUDE_MAX
        ):
            print(
                f"control_amplitude={value} is out of range "
                f"({CONTROL_AMPLITUDE_MIN}, {CONTROL_AMPLITUDE_MAX}), "
                f"using default={DEFAULT_CONTROL_AMPLITUDE}"
            )
            if param is None:
                self.input_parameters["control_amplitude"] = ParameterModel(
                    value=DEFAULT_CONTROL_AMPLITUDE,
                    unit="a.u.",
                    description="Control pulse amplitude (default)",
                )
            else:
                param.value = DEFAULT_CONTROL_AMPLITUDE

        return result

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["qubit_frequency"].value = result["resonant_frequencies"][label]
        self.output_parameters["control_amplitude"].value = result.get(
            "control_amplitude_used", DEFAULT_CONTROL_AMPLITUDE
        )
        self.output_parameters["readout_amplitude"].value = result.get(
            "readout_amplitude_used", self._get_readout_amplitude_value()
        )
        output_parameters = self.attach_execution_id(execution_id)
        base_fig = result["fig"][label]
        resonant_freq = result["resonant_frequencies"].get(label)
        marked_fig = go.Figure(base_fig)
        if resonant_freq is not None:
            marked_fig.add_vline(
                x=resonant_freq,
                line_width=1,
                line_color="red",
                line_dash="dash",
                annotation_text=f"f = {resonant_freq:.6f} GHz",
                annotation_position="top",
                annotation_font_color="red",
            )
        figures = [base_fig, marked_fig]

        qubit_freq = self.output_parameters["qubit_frequency"].value
        if qubit_freq is not None and qubit_freq < 2.5:
            error_msg = f"Qubit frequency too low for qid={qid}: {qubit_freq:.6f} GHz < 3.0 GHz"
            print(f"[ERROR] {error_msg}")
            return PostProcessResult(
                output_parameters=output_parameters,
                figures=figures,
                validation_error=error_msg,
            )

        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]

        readout_frequency = self.input_parameters["readout_frequency"]
        qubit_frequency = self.input_parameters["coarse_qubit_frequency"]
        assert readout_frequency is not None
        assert qubit_frequency is not None

        readout_amp = self._get_readout_amplitude_value()

        ca_param = self.input_parameters.get("control_amplitude")
        ctrl_amp_value = ca_param.value if ca_param is not None else DEFAULT_CONTROL_AMPLITUDE

        if (
            ctrl_amp_value is None
            or not isinstance(ctrl_amp_value, (int, float))
            or math.isnan(ctrl_amp_value)
            or ctrl_amp_value <= CONTROL_AMPLITUDE_MIN
            or ctrl_amp_value >= CONTROL_AMPLITUDE_MAX
        ):
            print(
                f"[run] control_amplitude={ctrl_amp_value} is invalid for {labels[0]}, "
                f"using default={DEFAULT_CONTROL_AMPLITUDE}"
            )
            ctrl_amp_value = DEFAULT_CONTROL_AMPLITUDE

        print(
            f"[run] CheckCoarseChevron params for {labels[0]}: "
            f"control_amplitude={ctrl_amp_value}, "
            f"coarse_qubit_frequency={qubit_frequency.value}, "
            f"readout_amplitude={readout_amp}, "
            f"readout_frequency={readout_frequency.value}"
        )

        label = labels[0]
        exp.params.readout_amplitude[label] = readout_amp
        with self._modified_qubit_readout_frequencies(
            exp,
            qubit_label=label,
            frequency_overrides={
                label: float(qubit_frequency.value),
                "R" + label: float(readout_frequency.value),
            },
        ):
            result = exp.chevron_pattern(
                amplitudes={labels[0]: ctrl_amp_value},
                frequencies={labels[0]: qubit_frequency.value},
                targets=labels,
                detuning_range=np.linspace(-0.075, 0.075, 31),
                time_range=np.arange(0, 101, 8),
            )

        self.save_calibration(backend)
        result["control_amplitude_used"] = ctrl_amp_value
        result["readout_amplitude_used"] = readout_amp
        return RunResult(raw_result=result)
