from typing import ClassVar

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.calibration.util import qid_to_cr_pair
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckBellStateTomography(BaseTask):
    """Task to check the bell state tomography."""

    name: str = "CheckBellStateTomography"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "bell_state_fidelity": OutputParameterModel(
            unit="a.u.",
            description="Bell state fidelity",
            value_type="float",
        ),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def make_figure(self, result: dict, qid: str) -> go.Figure:
        """Create a figure from the result."""
        # Assuming result contains a 'figure' key with the figure data
        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Re", "Im"),
        )

        # Real part
        fig.add_trace(
            go.Heatmap(
                z=result["density_matrix"].real,
                zmin=-1,
                zmax=1,
                colorscale="RdBu_r",
            ),
            row=1,
            col=1,
        )

        # Imaginary part
        fig.add_trace(
            go.Heatmap(
                z=result["density_matrix"].imag,
                zmin=-1,
                zmax=1,
                colorscale="RdBu_r",
            ),
            row=1,
            col=2,
        )
        fig.update_layout(
            title=f"Bell state tomography: {qid}",
            annotations=[
                {
                    "x": 0.5,
                    "y": 1.05,
                    "xref": "paper",
                    "yref": "paper",
                    "text": f"Fidelity: {result['fidelity']:.2f}",
                    "showarrow": False,
                }
            ],
            xaxis1={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "y1",
                "tickangle": 0,
            },
            yaxis1={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "x1",
                "autorange": "reversed",
            },
            xaxis2={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "y2",
                "tickangle": 0,
            },
            yaxis2={
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3],
                "ticktext": ["00", "01", "10", "11"],
                "scaleanchor": "x2",
                "autorange": "reversed",
            },
            width=600,
            height=356,
            margin={"l": 70, "r": 70, "t": 90, "b": 70},
        )
        return fig

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        result = run_result.raw_result
        self.output_parameters["bell_state_fidelity"].value = result["fidelity"]
        output_parameters = self.attach_execution_id(execution_id)
        result["figure"] = self.make_figure(result, qid)
        figures: list = [result["figure"]]
        raw_data: list = []
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, session: QubexSession, qid: str) -> RunResult:
        control, target = qid_to_cr_pair(qid)
        exp = session.get_session()
        result = exp.bell_state_tomography(control, target)
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
