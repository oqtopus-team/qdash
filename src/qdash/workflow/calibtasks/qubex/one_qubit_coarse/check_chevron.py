from collections.abc import Mapping
from typing import ClassVar

import numpy as np
import plotly.graph_objects as go
from qubex.experiment.experiment_constants import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    OutputPublishTarget,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_CONTROL_AMPLITUDE = 0.0625
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0


class CheckChevron(QubexTask):
    """Measure one fixed-grid Chevron pattern and estimate the qubit frequency."""

    name: str = "CheckChevron"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",)
        ),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",)
        ),
        "readout_amplitude": InputParameterSpec.required_database(),
        "control_amplitude": InputParameterSpec.database_or_default(
            default=DEFAULT_CONTROL_AMPLITUDE,
            greater_than_or_equal=CONTROL_AMPLITUDE_MIN,
            less_than_or_equal=CONTROL_AMPLITUDE_MAX,
            unit="a.u.",
            description="Control pulse amplitude",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "detuning_range": RunParameterSpec(
            unit="GHz",
            value_type="np.linspace",
            default=(-0.05, 0.05, 51),
            description="Drive-frequency detuning sweep around control_frequency",
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="range",
            default=(0, 401, 8),
            description="Control-pulse duration sweep",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Number of shots per Chevron sweep point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qubit_frequency": OutputParameterSpec(
            unit="GHz",
            description="Qubit bare frequency estimated from the Chevron fit",
            publish_targets=(
                OutputPublishTarget(parameter_name="qubit_frequency", role="measurement"),
                OutputPublishTarget(parameter_name="control_frequency", role="operational"),
            ),
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        data = getattr(result, "data", result)
        if not isinstance(data, Mapping):
            raise TypeError(
                f"chevron_pattern returned unsupported data type: {type(data).__name__}"
            )

        resonant_frequencies = data.get("resonant_frequencies")
        if not isinstance(resonant_frequencies, Mapping) or label not in resonant_frequencies:
            raise ValueError(f"CheckChevron produced no resonant frequency for {label}")
        resonant_frequency = float(resonant_frequencies[label])
        self.output_parameters["qubit_frequency"].value = resonant_frequency
        output_parameters = self.attach_execution_id(execution_id)

        figures_map = getattr(result, "figures", None)
        base_figure = figures_map.get(label) if isinstance(figures_map, Mapping) else None
        figures: list[go.Figure] = []
        if base_figure is not None:
            figures.append(base_figure)
            marked_figure = go.Figure(base_figure)
            marked_figure.add_vline(
                x=resonant_frequency,
                line_width=1,
                line_color="red",
                line_dash="dash",
                annotation_text=f"f = {resonant_frequency:.6f} GHz",
                annotation_position="top",
                annotation_font_color="red",
            )
            figures.append(marked_figure)

        validation_error = None
        if resonant_frequency < 2.5:
            validation_error = (
                f"Qubit frequency too low for qid={qid}: {resonant_frequency:.6f} GHz < 2.5 GHz"
            )
            print(f"[ERROR] {validation_error}")

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            validation_error=validation_error,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = exp.get_qubit_label(int(qid))

        control_frequency = self._required_input_value("control_frequency")
        readout_frequency = self._required_input_value("readout_frequency")
        readout_amplitude = self._required_input_value("readout_amplitude")
        control_amplitude = self._required_input_value("control_amplitude")

        print(
            f"[run] CheckChevron params for {label}: "
            f"control_amplitude={control_amplitude}, "
            f"control_frequency={control_frequency}, "
            f"readout_amplitude={readout_amplitude}, "
            f"readout_frequency={readout_frequency}"
        )

        exp.params.readout_amplitude[label] = readout_amplitude
        with self._modified_qubit_readout_frequencies(
            exp,
            qubit_label=label,
            frequency_overrides={label: control_frequency, "R" + label: readout_frequency},
        ):
            result = exp.chevron_pattern(
                targets=[label],
                frequencies={label: control_frequency},
                amplitudes={label: control_amplitude},
                detuning_range=self.run_parameters["detuning_range"].get_value(),
                time_range=self.run_parameters["time_range"].get_value(),
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                plot=False,
                save_image=False,
            )

        self.save_calibration(backend)
        return RunResult(raw_result=result, r2={qid: self._mean_rabi_fit_r2(result, label)})

    @staticmethod
    def _mean_rabi_fit_r2(result: object, label: str) -> float | None:
        data = getattr(result, "data", result)
        if not isinstance(data, Mapping):
            return None

        r2_by_target = data.get("rabi_fit_r2")
        if not isinstance(r2_by_target, Mapping) or label not in r2_by_target:
            return None

        r2_values = np.asarray(r2_by_target[label], dtype=float).reshape(-1)
        finite_r2_values = r2_values[np.isfinite(r2_values)]
        if finite_r2_values.size == 0:
            return None
        return float(np.mean(finite_r2_values))

    def _required_input_value(self, name: str) -> float:
        parameter = self.input_parameters[name]
        if parameter is None or parameter.value is None:
            raise ValueError(f"{name} input parameter is required")
        return float(parameter.value)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        raise NotImplementedError(f"{self.name} does not support batch execution")
