from typing import Any, ClassVar

import numpy as np
import plotly.graph_objects as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.caltasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.caltasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class ChevronPattern(QubexTask):
    """Task to check the chevron pattern."""

    name: str = "ChevronPattern"
    task_type: str = "qubit"
    timeout: int = 60 * 240
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "qubit_frequency": OutputParameterModel(unit="GHz", description="Qubit bare frequency"),
    }

    def make_figure(self, result: Any, label: str) -> go.Figure:
        """Create a figure for the results."""

        detuning_range = result["detuning_range"]
        time_range = result["time_range"]
        frequencies = result["frequencies"]

        result["rabi_rates"]
        chevron_data = result["chevron_data"]

        fig = go.Figure()
        fig.add_trace(
            go.Heatmap(
                x=detuning_range + frequencies[label],
                y=time_range,
                z=chevron_data[label],
                colorscale="Viridis",
            )
        )
        fig.update_layout(
            title=dict(
                text=f"Chevron pattern : {label}",
                subtitle=dict(
                    text="control_amplitude=",
                    font=dict(
                        size=13,
                        family="monospace",
                    ),
                ),
            ),
            xaxis_title="Drive frequency (GHz)",
            yaxis_title="Time (ns)",
            width=600,
            height=400,
            margin=dict(t=80),
        )

        return fig

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["qubit_frequency"].value = result["resonant_frequencies"][label]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [self.make_figure(result, label)]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]

        # Apply parameter overrides if provided via task_details
        # Supports: qubit_frequency, readout_amplitude, control_amplitude, readout_frequency
        with self._apply_parameter_overrides(backend, qid):
            result = exp.chevron_pattern(
                targets=labels,
                detuning_range=np.linspace(-0.05, 0.05, 51),
                time_range=np.arange(0, 201, 4),
                # rabi_params={labels[0]: rabi_param},
            )

        self.save_calibration(backend)
        return RunResult(raw_result=result)
