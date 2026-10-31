from collections.abc import Mapping
from typing import Any, ClassVar, cast

import plotly.graph_objects as go
from qubex.contrib.experiment import estimate_qubit_frequency_from_chevron
from qubex.experiment.experiment_constants import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.calibtasks.qubex.validation import finite_value_error, first_validation_error
from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_CONTROL_AMPLITUDE = 0.0625
DEFAULT_MINIMUM_PEAK_BACKGROUND_RMS_RATIO = 5.0
DEFAULT_TARGET_OMEGA_RABI = 0.0125
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0


class CheckChevron(QubexTask):
    """Estimate qubit frequency and control amplitude from a fixed-grid Chevron."""

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
            default=(-0.05, 0.05, 41),
            description="Drive-frequency detuning sweep around control_frequency",
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="np.linspace",
            default=(0, 250, 26),
            description="Control-pulse duration sweep",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS // 4,
            description="Number of shots per Chevron sweep point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
        "target_omega_rabi": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=DEFAULT_TARGET_OMEGA_RABI,
            description="Target Rabi frequency used to estimate control amplitude",
        ),
        "minimum_peak_background_rms_ratio": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=DEFAULT_MINIMUM_PEAK_BACKGROUND_RMS_RATIO,
            description="Minimum matched-transform peak/background RMS ratio",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qubit_frequency": OutputParameterSpec(
            unit="GHz",
            description="Qubit bare frequency estimated by matched-transform analysis",
            publish_targets=(
                "qubit_frequency",
                "control_frequency",
            ),
        ),
        "control_amplitude": OutputParameterSpec(
            unit="a.u.",
            description="Control pulse amplitude estimated for the target Rabi frequency",
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
                "estimate_qubit_frequency_from_chevron returned "
                f"unsupported data type: {type(data).__name__}"
            )

        resonant_frequency = self._target_value(data, "resonant_frequencies", label)
        omega_rabi = self._target_value(data, "omega_rabis", label)
        amplitude_used = self._target_value(data, "amplitudes_used", label)
        peak_background_rms_ratio = self._target_value(data, "peak_background_rms_ratios", label)
        target_omega_rabi = self.run_parameters["target_omega_rabi"].value
        threshold = self.run_parameters["minimum_peak_background_rms_ratio"].value

        frequency_value_error = finite_value_error(
            resonant_frequency,
            f"CheckChevron qubit frequency for {label}",
        )
        frequency_error = finite_value_error(
            resonant_frequency,
            f"CheckChevron qubit frequency for {label}",
            minimum=2.5,
        )
        omega_rabi_error = self._positive_value_error(
            omega_rabi, f"CheckChevron Rabi frequency for {label}"
        )
        amplitude_used_error = finite_value_error(
            amplitude_used,
            f"CheckChevron control amplitude used for {label}",
            minimum=CONTROL_AMPLITUDE_MIN,
            maximum=CONTROL_AMPLITUDE_MAX,
        )
        target_omega_rabi_error = self._positive_value_error(target_omega_rabi, "target_omega_rabi")
        threshold_error = finite_value_error(
            threshold,
            "minimum_peak_background_rms_ratio",
            minimum=0.0,
        )
        ratio_error = finite_value_error(
            peak_background_rms_ratio,
            f"CheckChevron peak/background RMS ratio for {label}",
            minimum=(
                float(cast("int | float | str", threshold)) if threshold_error is None else None
            ),
        )

        target_control_amplitude: float | None = None
        if (
            omega_rabi_error is None
            and amplitude_used_error is None
            and target_omega_rabi_error is None
        ):
            amplitude_used_value = float(cast("int | float | str", amplitude_used))
            target_omega_rabi_value = float(cast("int | float | str", target_omega_rabi))
            omega_rabi_value = float(cast("int | float | str", omega_rabi))
            target_control_amplitude = (
                amplitude_used_value * target_omega_rabi_value / omega_rabi_value
            )
            target_control_amplitude = min(
                max(target_control_amplitude, CONTROL_AMPLITUDE_MIN),
                CONTROL_AMPLITUDE_MAX,
            )

        resonant_frequency_value = (
            float(cast("int | float | str", resonant_frequency))
            if frequency_value_error is None
            else None
        )
        self.output_parameters["qubit_frequency"].value = resonant_frequency_value
        self.output_parameters["control_amplitude"].value = target_control_amplitude
        output_parameters = self.attach_execution_id(execution_id)

        figures_map = getattr(result, "figures", None)
        figures: list[go.Figure] = []
        if isinstance(figures_map, Mapping):
            measurement_figure = figures_map.get(f"{label}_measurement")
            transform_figure = figures_map.get(f"{label}_transform")
            if measurement_figure is not None:
                figures.append(measurement_figure)
                if resonant_frequency_value is not None:
                    marked_figure = go.Figure(measurement_figure)
                    marked_figure.add_vline(
                        x=resonant_frequency_value,
                        line_width=1,
                        line_color="red",
                        line_dash="dash",
                        annotation_text=f"f = {resonant_frequency_value:.6f} GHz",
                        annotation_position="top",
                        annotation_font_color="red",
                    )
                    figures.append(marked_figure)
            if transform_figure is not None:
                figures.append(transform_figure)

        validation_error = first_validation_error(
            frequency_error,
            threshold_error,
            ratio_error,
            omega_rabi_error,
            amplitude_used_error,
            target_omega_rabi_error,
        )
        if validation_error is not None:
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
            result = estimate_qubit_frequency_from_chevron(
                exp=exp,
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
        return RunResult(raw_result=result)

    @staticmethod
    def _target_value(data: Mapping[str, Any], key: str, label: str) -> Any:
        values = data.get(key)
        if not isinstance(values, Mapping):
            return None
        return values.get(label)

    @staticmethod
    def _positive_value_error(value: Any, name: str) -> str | None:
        error = finite_value_error(value, name, minimum=0.0)
        if error is not None:
            return error
        if float(value) == 0.0:
            return f"{name} must be positive: {value}"
        return None

    def _required_input_value(self, name: str) -> float:
        parameter = self.input_parameters[name]
        if parameter is None or parameter.value is None:
            raise ValueError(f"{name} input parameter is required")
        return float(parameter.value)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        raise NotImplementedError(f"{self.name} does not support batch execution")
