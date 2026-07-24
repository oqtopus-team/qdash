import math
from collections.abc import Mapping
from typing import Any, ClassVar

import plotly.graph_objects as go
from qubex.contrib.experiment import estimate_qubit_frequency_from_chevron_adaptive
from qubex.measurement.measurement_defaults import DEFAULT_READOUT_DURATION

from qdash.datamodel.task import ParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_COARSE_CONTROL_AMPLITUDE = 0.0625
CONTROL_AMPLITUDE_MIN = 1e-4
CONTROL_AMPLITUDE_MAX = 1.0


class CheckChevron(QubexTask):
    """Adaptive chevron task for coarse qubit-frequency estimation."""

    name: str = "CheckChevron"
    task_type: str = "qubit"
    timeout: int = 60 * 240
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "coarse_qubit_frequency": None,
        "readout_frequency": None,
        "readout_amplitude": None,
        "coarse_control_amplitude": ParameterModel(
            value=DEFAULT_COARSE_CONTROL_AMPLITUDE,
            unit="a.u.",
            description="Coarse control pulse amplitude",
        ),
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION,
            unit="ns",
            description="Readout pulse length",
        ),
    }
    run_parameters: ClassVar[dict[str, Any]] = {}
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(unit="GHz", description="Qubit bare frequency (coarse)"),
        "control_amplitude": ParameterModel(
            unit="a.u.", description="Control pulse amplitude estimated by adaptive chevron"
        ),
    }

    def preprocess(self, backend: QubexBackend, qid: str) -> PreProcessResult:
        result = super().preprocess(backend, qid)

        param = self.input_parameters.get("coarse_control_amplitude")
        value = param.value if param is not None else None
        if (
            value is None
            or not isinstance(value, (int, float))
            or math.isnan(value)
            or value <= CONTROL_AMPLITUDE_MIN
            or value >= CONTROL_AMPLITUDE_MAX
        ):
            print(
                f"coarse_control_amplitude={value} is out of range "
                f"({CONTROL_AMPLITUDE_MIN}, {CONTROL_AMPLITUDE_MAX}), "
                f"using default={DEFAULT_COARSE_CONTROL_AMPLITUDE}"
            )
            if param is None:
                self.input_parameters["coarse_control_amplitude"] = ParameterModel(
                    value=DEFAULT_COARSE_CONTROL_AMPLITUDE,
                    unit="a.u.",
                    description="Coarse control pulse amplitude (default)",
                )
            else:
                param.value = DEFAULT_COARSE_CONTROL_AMPLITUDE

        return result

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result

        resonant_freq = result["resonant_frequencies"][label]
        self.output_parameters["qubit_frequency"].value = resonant_freq
        self.output_parameters["control_amplitude"].value = result.get(
            "control_amplitude_used", DEFAULT_COARSE_CONTROL_AMPLITUDE
        )
        output_parameters = self.attach_execution_id(execution_id)

        figures = self._build_figures(result, label, resonant_freq)
        if resonant_freq < 2.5:
            error_msg = f"Qubit frequency too low for qid={qid}: {resonant_freq:.6f} GHz < 2.5 GHz"
            print(f"[ERROR] {error_msg}")
            return PostProcessResult(
                output_parameters=output_parameters,
                figures=figures,
                validation_error=error_msg,
            )

        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = exp.get_qubit_label(int(qid))

        readout_frequency = self.input_parameters["readout_frequency"]
        qubit_frequency = self.input_parameters["coarse_qubit_frequency"]
        readout_amplitude = self.input_parameters["readout_amplitude"]
        assert readout_frequency is not None
        assert qubit_frequency is not None
        if qubit_frequency.value is None:
            raise ValueError("coarse_qubit_frequency input parameter is required")
        if readout_frequency.value is None:
            raise ValueError("readout_frequency input parameter is required")
        if readout_amplitude is None or readout_amplitude.value is None:
            raise ValueError("readout_amplitude input parameter is required")
        qubit_freq = float(qubit_frequency.value)
        readout_freq = float(readout_frequency.value)
        readout_amp = float(readout_amplitude.value)

        ca_param = self.input_parameters.get("coarse_control_amplitude")
        ctrl_amp_value = (
            ca_param.value if ca_param is not None else DEFAULT_COARSE_CONTROL_AMPLITUDE
        )
        if (
            ctrl_amp_value is None
            or not isinstance(ctrl_amp_value, (int, float))
            or math.isnan(ctrl_amp_value)
            or ctrl_amp_value <= CONTROL_AMPLITUDE_MIN
            or ctrl_amp_value >= CONTROL_AMPLITUDE_MAX
        ):
            print(
                f"[run] coarse_control_amplitude={ctrl_amp_value} is invalid for {label}, "
                f"using default={DEFAULT_COARSE_CONTROL_AMPLITUDE}"
            )
            ctrl_amp_value = DEFAULT_COARSE_CONTROL_AMPLITUDE

        print(
            f"[run] CheckChevron params for {label}: "
            f"coarse_control_amplitude={ctrl_amp_value}, "
            f"coarse_qubit_frequency={qubit_freq}, "
            f"readout_amplitude={readout_amp}, "
            f"readout_frequency={readout_freq}"
        )

        exp.params.readout_amplitude[label] = readout_amp
        with self._modified_qubit_readout_frequencies(
            exp,
            qubit_label=label,
            frequency_overrides={label: qubit_freq, "R" + label: readout_freq},
        ):
            result = self._run_adaptive_chevron(
                exp=exp,
                label=label,
                qubit_frequency=qubit_freq,
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
            plot=False,
            save_image=False,
        )
        result_data = self._adaptive_result_data(adaptive_result)
        result_data["control_amplitude_used"] = self._control_amplitude_from_result(
            result_data, label, control_amplitude
        )
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

    def _control_amplitude_from_result(
        self, result: Mapping[str, Any], label: str, fallback: float
    ) -> float:
        for key in ("target_amplitudes", "amplitudes_used"):
            values = result.get(key)
            if isinstance(values, Mapping) and label in values:
                return float(values[label])

        results = result.get("results")
        if isinstance(results, Mapping):
            per_target = results.get(label)
            if isinstance(per_target, Mapping) and "amplitude_used" in per_target:
                return float(per_target["amplitude_used"])

        return fallback

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
