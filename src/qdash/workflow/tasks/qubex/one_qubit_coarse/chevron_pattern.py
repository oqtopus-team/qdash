from typing import Any, ClassVar

import numpy as np
import plotly.graph_objects as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class ChevronPattern(QubexTask):
    """Task to check the chevron pattern."""

    name: str = "ChevronPattern"
    task_type: str = "qubit"
    timeout: int = 60 * 240
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "bare_frequency": OutputParameterModel(unit="GHz", description="Qubit bare frequency"),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        self.input_parameters["readout_amplitude"] = InputParameterModel(
            unit="a.u.",
            description="Readout Frequency",
            value=exp.experiment_system.control_params.get_readout_amplitude(label),
            value_type="float",
        )
        self.input_parameters["readout_frequency"] = InputParameterModel(
            unit="GHz",
            description="Readout Amplitude",
            value=exp.experiment_system.quantum_system.get_resonator(exp.get_resonator_label(int(qid))).frequency,
            value_type="float",
        )
        return PreProcessResult(input_parameters=self.input_parameters)

    def make_figure(self, result: Any, label: str) -> go.Figure:
        """Create a figure for the results."""

        detuning_range = result["detuning_range"]
        time_range = result["time_range"]
        frequencies = result["frequencies"]

        rabi_rates = result["rabi_rates"]
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
                    text=f"control_amplitude=",
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
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        exp = self.get_experiment(session)
        label = self.get_qubit_label(session, qid)
        result = run_result.raw_result
        self.output_parameters["bare_frequency"].value = result["resonant_frequencies"][label]
        output_parameters = self.attach_execution_id(execution_id)
        figures = [self.make_figure(result, label)]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: QubexSession, qid: str) -> RunResult:
        exp = self.get_experiment(session)
        labels = [exp.get_qubit_label(int(qid))]
        from qubex.experiment.rabi_param import RabiParam

        # rabi_param = RabiParam(
        #     **{
        #         "amplitude": 0.018757924680085324,
        #         "angle": 0.2550564567234854,
        #         "distance": -0.013257740996778011,
        #         "frequency": 0.012516133217763476,
        #         "noise": 0.00035153969656676054,
        #         "offset": 0.0009658521547125462,
        #         "phase": -0.02116097291450829,
        #         "r2": 0.99857055386212,
        #         "reference_phase": 2.403657416868579,
        #         "target": "Q04",
        #     }
        # )
        result = exp.chevron_pattern(
            targets=labels,
            detuning_range=np.linspace(-0.05, 0.05, 51),
            time_range=np.arange(0, 201, 4),
            # rabi_params={labels[0]: rabi_param},
        )
        self.save_calibration(session)
        return RunResult(raw_result=result)
