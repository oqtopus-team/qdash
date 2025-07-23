from typing import ClassVar

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckReadoutAmplitude(BaseTask):
    """Task to check the readout amplitude."""

    name: str = "CheckReadoutAmplitude"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "amplitude_range": InputParameterModel(
            unit="a.u.",
            value_type="np.linspace",
            value=(0.0, 0.2, 51),
            description="Amplitude range for readout",
        )
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def make_figure(self, signal: dict, noise: dict, snr: dict, label: str) -> go.Figure:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True)
        fig.add_trace(
            go.Scatter(
                x=self.input_parameters["amplitude_range"].get_value(),
                y=signal[label],
                mode="lines+markers",
                name="Signal",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=self.input_parameters["amplitude_range"].get_value(),
                y=noise[label],
                mode="lines+markers",
                name="Noise",
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=self.input_parameters["amplitude_range"].get_value(),
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

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result = run_result.raw_result
        signal = result["signal"]
        noise = result["noise"]
        snr = result["snr"]
        figures = [self.make_figure(signal, noise, snr, label)]
        output_parameters = self.attach_execution_id(execution_id)
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""

    def batch_run(self, session: QubexSession, qids: list[str]) -> RunResult:
        """Run the task for a batch of qubits."""
        exp = session.get_session()
        labels = [exp.get_qubit_label(int(qid)) for qid in qids]
        result = exp.sweep_readout_amplitude(
            targets=labels, amplitude_range=self.input_parameters["amplitude_range"].get_value()
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
