from typing import Any, ClassVar

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend

DEFAULT_SNR_THRESHOLD = 1.0


class CheckReadoutAmplitude(QubexTask):
    """Task to check the readout amplitude."""

    name: str = "CheckReadoutAmplitude"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "amplitude_range": RunParameterModel(
            unit="a.u.",
            value_type="np.linspace",
            value=(0.0, 0.2, 51),
            description="Amplitude range for readout",
        ),
        "snr_threshold": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=DEFAULT_SNR_THRESHOLD,
            description="SNR threshold for determining readout amplitude",
        ),
    }
    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "readout_amplitude": ParameterModel(
            unit="a.u.", description="Optimal readout amplitude from SNR threshold"
        ),
    }

    def make_figure(
        self, signal: dict[str, Any], noise: dict[str, Any], snr: dict[str, Any], label: str
    ) -> go.Figure:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True)
        fig.add_trace(
            go.Scatter(
                x=self.run_parameters["amplitude_range"].get_value(),
                y=signal[label],
                mode="lines+markers",
                name="Signal",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=self.run_parameters["amplitude_range"].get_value(),
                y=noise[label],
                mode="lines+markers",
                name="Noise",
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=self.run_parameters["amplitude_range"].get_value(),
                y=snr[label],
                mode="lines+markers",
                name="SNR",
            ),
            row=3,
            col=1,
        )
        fig.update_layout(
            title=f"Readout SNR : {label}",
            xaxis3_title="Readout amplitude (arb. units)",
            yaxis_title="Signal",
            yaxis2_title="Noise",
            yaxis3_title="SNR",
            showlegend=False,
            width=600,
            height=400,
        )
        return fig

    def _find_optimal_amplitude(self, snr_values: Any) -> float | None:
        """Find the optimal readout amplitude via linear interpolation at SNR threshold.

        Args:
            snr_values: SNR array for a single qubit.

        Returns:
            Interpolated amplitude where SNR crosses the threshold, or None.
        """
        amplitude_range = self.run_parameters["amplitude_range"].get_value()
        threshold = self.run_parameters["snr_threshold"].get_value()
        snr_array = np.asarray(snr_values)
        idx = np.where(snr_array > threshold)[0]
        if len(idx) == 0:
            return None
        i = idx[0]
        if i > 0:
            x1, x2 = amplitude_range[i - 1], amplitude_range[i]
            y1, y2 = snr_array[i - 1], snr_array[i]
            return float(x1 + (threshold - y1) * (x2 - x1) / (y2 - y1))
        return float(amplitude_range[i])

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        signal = result["signal"]
        noise = result["noise"]
        snr = result["snr"]

        optimal_amp = self._find_optimal_amplitude(snr[label])
        if optimal_amp is not None:
            self.output_parameters["readout_amplitude"].value = optimal_amp
            print(f"readout_amplitude={optimal_amp:.6f} (SNR threshold interpolation)")
        else:
            print(f"WARNING: SNR never exceeded threshold for {label}, readout_amplitude not set")

        figures = [self.make_figure(signal, noise, snr, label)]
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the task."""
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = exp.sweep_readout_amplitude(
            targets=[label],
            amplitude_range=self.run_parameters["amplitude_range"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)

    def batch_run(self, backend: QubexBackend, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = self.get_experiment(backend)
        labels = [self.get_qubit_label(backend, qid) for qid in qids]
        result = exp.sweep_readout_amplitude(
            targets=labels, amplitude_range=self.run_parameters["amplitude_range"].get_value()
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
