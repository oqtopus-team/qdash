from collections.abc import Mapping
from typing import Any, ClassVar, cast

import plotly.graph_objects as go
from qubex.contrib.experiment import estimate_qubit_frequency_from_chevron_adaptive
from qubex.experiment.experiment_constants import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    OutputPublishTarget,
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

DEFAULT_MINIMUM_PEAK_BACKGROUND_RMS_RATIO = 5.0
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0


class CheckAdaptiveChevron(QubexTask):
    """Adaptive chevron task for coarse qubit-frequency estimation."""

    name: str = "CheckAdaptiveChevron"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("coarse_qubit_frequency",)
        ),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",)
        ),
        "readout_amplitude": InputParameterSpec.required_database(),
        "coarse_control_amplitude": InputParameterSpec.required_database(
            greater_than_or_equal=CONTROL_AMPLITUDE_MIN,
            less_than_or_equal=CONTROL_AMPLITUDE_MAX,
            unit="a.u.",
            description="Coarse control pulse amplitude",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS // 4,
            description="Number of shots for adaptive chevron search and final sweeps",
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
            default=DEFAULT_MINIMUM_PEAK_BACKGROUND_RMS_RATIO,
            description=("Minimum final peak/background RMS ratio required to accept the result"),
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qubit_frequency": OutputParameterSpec(
            unit="GHz",
            description="Qubit bare frequency (coarse)",
            publish_targets=(
                OutputPublishTarget(parameter_name="qubit_frequency", role="measurement"),
                OutputPublishTarget(parameter_name="control_frequency", role="operational"),
            ),
        ),
        "control_amplitude": OutputParameterSpec(
            unit="a.u.", description="Control pulse amplitude estimated by adaptive chevron"
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result

        resonant_freq = result["resonant_frequencies"][label]
        target_amplitude = self._target_control_amplitude(result, label)
        target_amplitude_error = finite_value_error(
            target_amplitude,
            f"CheckAdaptiveChevron target control amplitude for {label}",
        )
        self.output_parameters["qubit_frequency"].value = resonant_freq
        self.output_parameters["control_amplitude"].value = (
            float(cast("int | float | str", target_amplitude))
            if target_amplitude_error is None
            else None
        )
        output_parameters = self.attach_execution_id(execution_id)

        figures = self._build_figures(result, label, resonant_freq)
        validation_error = self._validation_error(
            result, label, qid, resonant_freq, target_amplitude_error
        )
        if validation_error is not None:
            print(f"[ERROR] {validation_error}")
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
            validation_error=validation_error,
        )

    def _validation_error(
        self,
        result: Mapping[str, Any],
        label: str,
        qid: str,
        resonant_freq: float,
        target_amplitude_error: str | None,
    ) -> str | None:
        if resonant_freq < 2.5:
            return f"Qubit frequency too low for qid={qid}: {resonant_freq:.6f} GHz < 2.5 GHz"

        threshold = self.run_parameters["minimum_peak_background_rms_ratio"].value
        ratios = result.get("peak_background_rms_ratios")
        ratio = ratios.get(label) if isinstance(ratios, Mapping) else None
        threshold_error = finite_value_error(
            threshold,
            "minimum_peak_background_rms_ratio",
            minimum=0.0,
        )
        return first_validation_error(
            threshold_error,
            finite_value_error(
                ratio,
                f"CheckAdaptiveChevron peak/background RMS ratio for {label}",
                minimum=(
                    float(cast("int | float | str", threshold)) if threshold_error is None else None
                ),
            ),
            target_amplitude_error,
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = exp.get_qubit_label(int(qid))

        readout_frequency = self.input_parameters["readout_frequency"]
        control_frequency = self.input_parameters["control_frequency"]
        readout_amplitude = self.input_parameters["readout_amplitude"]
        assert readout_frequency is not None
        assert control_frequency is not None
        if control_frequency.value is None:
            raise ValueError("control_frequency input parameter is required")
        if readout_frequency.value is None:
            raise ValueError("readout_frequency input parameter is required")
        if readout_amplitude is None or readout_amplitude.value is None:
            raise ValueError("readout_amplitude input parameter is required")
        control_freq = float(control_frequency.value)
        readout_freq = float(readout_frequency.value)
        readout_amp = float(readout_amplitude.value)

        control_amplitude = self.input_parameters["coarse_control_amplitude"].value
        if control_amplitude is None:
            raise ValueError("coarse_control_amplitude input parameter is required")
        ctrl_amp_value = float(control_amplitude)

        print(
            f"[run] CheckAdaptiveChevron params for {label}: "
            f"coarse_control_amplitude={ctrl_amp_value}, "
            f"control_frequency={control_freq}, "
            f"readout_amplitude={readout_amp}, "
            f"readout_frequency={readout_freq}"
        )

        exp.params.readout_amplitude[label] = readout_amp
        with self._modified_qubit_readout_frequencies(
            exp,
            qubit_label=label,
            frequency_overrides={label: control_freq, "R" + label: readout_freq},
        ):
            result = self._run_adaptive_chevron(
                exp=exp,
                label=label,
                qubit_frequency=control_freq,
                control_amplitude=float(ctrl_amp_value),
            )

        self.save_calibration(backend)
        result["readout_amplitude_used"] = readout_amp
        return RunResult(raw_result=result)

    def _run_adaptive_chevron(
        self,
        *,
        exp: Any,
        label: str,
        qubit_frequency: float,
        control_amplitude: float,
    ) -> dict[str, Any]:
        adaptive_result = estimate_qubit_frequency_from_chevron_adaptive(
            exp=exp,
            targets=[label],
            frequencies={label: qubit_frequency},
            amplitudes={label: control_amplitude},
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
            plot=False,
            save_image=False,
        )
        result_data = self._adaptive_result_data(adaptive_result)
        result_data["figures"] = getattr(adaptive_result, "figures", {})
        return result_data

    def _adaptive_result_data(self, adaptive_result: Any) -> dict[str, Any]:
        data = getattr(adaptive_result, "data", adaptive_result)
        if not isinstance(data, Mapping):
            raise TypeError(
                "estimate_qubit_frequency_from_chevron_adaptive returned "
                f"unsupported data type: {type(data).__name__}"
            )
        return dict(data)

    @staticmethod
    def _target_control_amplitude(result: Mapping[str, Any], label: str) -> Any:
        target_amplitudes = result.get("target_amplitudes")
        if not isinstance(target_amplitudes, Mapping):
            return None
        return target_amplitudes.get(label)

    def _build_figures(
        self, result: Mapping[str, Any], label: str, resonant_freq: float
    ) -> list[go.Figure]:
        figures_map = result.get("figures")
        if isinstance(figures_map, Mapping):
            preferred_keys = [
                f"{label}_measurement",
                f"{label}_transform",
                f"{label}_search_measurement",
                f"{label}_search_transform",
                f"{label}_rough_measurement",
                f"{label}_rough_transform",
            ]
            figures: list[go.Figure] = []
            ordered_keys = preferred_keys + [
                key for key in figures_map if isinstance(key, str) and key not in preferred_keys
            ]
            for key in ordered_keys:
                figure = figures_map.get(key)
                if figure is None:
                    continue
                figures.append(figure)
                if key == f"{label}_measurement":
                    marked_fig = go.Figure(figure)
                    marked_fig.add_vline(
                        x=resonant_freq,
                        line_width=1,
                        line_color="red",
                        line_dash="dash",
                        annotation_text=f"f = {resonant_freq:.6f} GHz",
                        annotation_position="top",
                        annotation_font_color="red",
                    )
                    figures.append(marked_fig)
            if figures:
                return figures

        fig_dict = result.get("fig")
        if isinstance(fig_dict, Mapping):
            base_fig = fig_dict.get(label)
            if base_fig is not None:
                marked_fig = go.Figure(base_fig)
                marked_fig.add_vline(
                    x=resonant_freq,
                    line_width=1,
                    line_color="red",
                    line_dash="dash",
                    annotation_text=f"f = {resonant_freq:.6f} GHz",
                    annotation_position="top",
                    annotation_font_color="red",
                )
                return [base_fig, marked_fig]

        return []

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        raise NotImplementedError(f"{self.name} does not support batch execution")
