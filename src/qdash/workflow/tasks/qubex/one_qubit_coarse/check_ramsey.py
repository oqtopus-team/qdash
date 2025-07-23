from typing import Any, ClassVar

import plotly.graph_objects as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckRamsey(BaseTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRamsey"
    backend: str = "qubex"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "detuning": InputParameterModel(
            unit="GHz",
            value_type="float",
            value=0.001,
            description="Detuning for Ramsey oscillation",
        ),
        "time_range": InputParameterModel(
            unit="ns",
            value_type="np.arange",
            value=(0, 10001, 100),
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "ramsey_frequency": OutputParameterModel(
            unit="MHz", description="Ramsey oscillation frequency"
        ),
        "bare_frequency": OutputParameterModel(unit="GHz", description="Qubit bare frequency"),
        "t2_star": OutputParameterModel(unit="μs", description="T2* time"),
    }

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def make_figure(self, result_x: Any, result_y: Any, label: str) -> go.Figure:
        """Create a figure for the results."""
        x_data = result_x.normalized.astype(float)
        y_data = result_y.normalized.astype(float)
        sweep = result_x.sweep_range.astype(float)

        # 色を sweep の逆順でカラーマップ化
        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=x_data,
                y=y_data,
                mode="markers+lines",
                marker={
                    "size": 6,
                    "color": sweep[::-1],
                    "colorscale": "Viridis",
                    "line": {"width": 0.5, "color": "DarkSlateGrey"},
                },
                text=[f"sweep: {s:.0f} ns" for s in sweep],
                hoverinfo="text+x+y",
                showlegend=False,
            )
        )

        fig.update_layout(
            title=f"Ramsey Interference in XY Plane : {label}",
            xaxis={
                "title": "⟨X⟩",
                "scaleanchor": "y",
                "scaleratio": 1,
                "showgrid": True,
                "gridcolor": "lightgray",
                "zeroline": True,
                "zerolinecolor": "gray",
            },
            yaxis={
                "title": "⟨Y⟩",
                "scaleanchor": "x",
                "scaleratio": 1,
                "showgrid": True,
                "gridcolor": "lightgray",
                "zeroline": True,
                "zerolinecolor": "gray",
            },
            width=700,
            height=700,
            plot_bgcolor="white",
            hovermode="closest",
            showlegend=False,
        )

        return fig

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process the results of the task."""
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result_x = run_result.raw_result["x"].data[label]
        result_y = run_result.raw_result["y"].data[label]
        self.output_parameters["ramsey_frequency"].value = (
            result_y.fit()["f"] * 1000
        )  # convert to MHz
        self.output_parameters["ramsey_frequency"].error = result_y.fit()["f_err"] * 1000
        self.output_parameters["bare_frequency"].value = result_y.bare_freq
        self.output_parameters["t2_star"].value = result_y.t2 * 0.001  # convert to μs
        self.output_parameters["t2_star"].error = result_y.fit()["tau_err"] * 0.001  # convert to μs
        output_parameters = self.attach_execution_id(execution_id)
        figures = [
            result_x.fit()["fig"],
            result_y.fit()["fig"],
            self.make_figure(result_x, result_y, label),
        ]
        raw_data = [result_y.data]
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, session: QubexSession, qid: str) -> RunResult:
        """Run the task."""
        exp = session.get_session()
        label = exp.get_qubit_label(int(qid))
        result_y = exp.ramsey_experiment(
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            detuning=self.input_parameters["detuning"].get_value(),
            second_rotation_axis="Y",  # Default axis for Ramsey
            spectator_state="0",
            targets=label,
        )
        result_x = exp.ramsey_experiment(
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            detuning=self.input_parameters["detuning"].get_value(),
            second_rotation_axis="X",  # Default axis for Ramsey
            spectator_state="0",
            targets=label,
        )
        exp.calib_note.save()
        result = {"x": result_x, "y": result_y}
        r2 = result_y.data[label].r2 if result_y.data else None
        return RunResult(raw_result=result, r2={qid: r2})

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
