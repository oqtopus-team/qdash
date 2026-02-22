from typing import Any, ClassVar

import numpy as np
import numpy.typing as npt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_READOUT_DURATION, DEFAULT_SHOTS


class CheckT2EchoAverage(QubexTask):
    """Task to measure T2 echo time multiple times and compute statistics.

    Runs T2 echo measurement n_runs times, computes mean and std,
    and generates a 4-panel fluctuation analysis figure.
    """

    name: str = "CheckT2EchoAverage"
    task_type: str = "qubit"
    timeout: int = 60 * 240  # 4 hours

    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": None,
        "hpi_amplitude": None,
        "hpi_length": None,
        "readout_amplitude": None,
        "readout_frequency": None,
        "readout_length": ParameterModel(
            value=DEFAULT_READOUT_DURATION, unit="ns", description="Readout pulse length"
        ),
    }

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="np.logspace",
            value=(np.log10(300), np.log10(100 * 1000), 51),
            description="Time range for T2 echo time",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for T2 echo time",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for T2 echo time",
        ),
        "n_runs": RunParameterModel(
            unit="",
            value_type="int",
            value=10,
            description="Number of T2 echo measurement repetitions",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "t2_echo_average": ParameterModel(unit="μs", description="Mean T2 echo time"),
        "t2_echo_std": ParameterModel(unit="μs", description="T2 echo standard deviation"),
    }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        label = labels[0]

        n_runs = int(self.run_parameters["n_runs"].get_value())

        t2_values = []
        t2_err_values = []
        r2_values = []
        results = []

        for i in range(n_runs):
            result = exp.t2_experiment(
                labels,
                time_range=self.run_parameters["time_range"].get_value(),
                shots=self.run_parameters["shots"].get_value(),
                interval=self.run_parameters["interval"].get_value(),
                save_image=False,
            )
            t2_values.append(result.data[label].t2 * 0.001)  # convert to μs
            t2_err_values.append(result.data[label].t2_err * 0.001)
            r2_values.append(result.data[label].r2)
            results.append(result)

        self.save_calibration(backend)

        r2_avg = float(np.mean(r2_values))
        return RunResult(
            raw_result={
                "t2_values": t2_values,
                "t2_err_values": t2_err_values,
                "r2_values": r2_values,
                "results": results,
                "label": label,
            },
            r2={qid: r2_avg},
        )

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        result = run_result.raw_result

        t2_values = np.array(result["t2_values"])
        t2_err_values = np.array(result["t2_err_values"])
        r2_values = np.array(result["r2_values"])
        results = result["results"]
        label = result["label"]

        t2_mean = float(np.mean(t2_values))
        t2_std = float(np.std(t2_values, ddof=1)) if len(t2_values) > 1 else 0.0

        self.output_parameters["t2_echo_average"].value = t2_mean
        self.output_parameters["t2_echo_average"].error = t2_std
        self.output_parameters["t2_echo_std"].value = t2_std

        output_parameters = self.attach_execution_id(execution_id)

        fluctuation_fig = self._make_fluctuation_figure(t2_values, t2_err_values, r2_values, qid)
        figures = [fluctuation_fig]
        for r in results:
            figures.append(r.data[label].fit()["fig"])

        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def _make_fluctuation_figure(
        self,
        t2_values: npt.NDArray[np.floating[Any]],
        t2_err_values: npt.NDArray[np.floating[Any]],
        r2_values: npt.NDArray[np.floating[Any]],
        qid: str,
    ) -> go.Figure:
        """Create a 4-panel fluctuation analysis figure."""
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "T2 Echo Time Series",
                "Relative Fluctuation (%)",
                "T2 Echo Histogram",
                "R² per Run",
            ),
        )

        runs = np.arange(1, len(t2_values) + 1)
        t2_mean = float(np.mean(t2_values))

        # Panel 1: T2 time series with error bars, mean line
        fig.add_trace(
            go.Scatter(
                x=runs,
                y=t2_values,
                error_y={"type": "data", "array": t2_err_values, "visible": True},
                mode="markers+lines",
                name="T2 Echo",
                marker={"size": 6},
            ),
            row=1,
            col=1,
        )
        fig.add_hline(
            y=t2_mean,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Mean: {t2_mean:.1f} μs",
            row=1,
            col=1,
        )

        # Panel 2: Relative fluctuation from mean (%)
        rel_fluct = (t2_values - t2_mean) / t2_mean * 100
        fig.add_trace(
            go.Scatter(
                x=runs,
                y=rel_fluct,
                mode="markers+lines",
                name="Fluctuation",
                marker={"size": 6, "color": "green"},
            ),
            row=1,
            col=2,
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=2)

        # Panel 3: T2 histogram
        fig.add_trace(
            go.Histogram(
                x=t2_values,
                name="T2 Echo Distribution",
                marker_color="steelblue",
            ),
            row=2,
            col=1,
        )

        # Panel 4: R² per run with threshold line
        fig.add_trace(
            go.Scatter(
                x=runs,
                y=r2_values,
                mode="markers+lines",
                name="R²",
                marker={"size": 6, "color": "purple"},
            ),
            row=2,
            col=2,
        )
        fig.add_hline(
            y=self.r2_threshold,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Threshold: {self.r2_threshold}",
            row=2,
            col=2,
        )

        t2_std = float(np.std(t2_values, ddof=1)) if len(t2_values) > 1 else 0.0
        t2_cv = (t2_std / t2_mean * 100) if t2_mean > 0 else 0.0
        fig.update_layout(
            title_text=(
                f"T2 Echo Fluctuation - {qid} "
                f"(Mean: {t2_mean:.1f}, Std: {t2_std:.1f}, CV: {t2_cv:.1f}%)"
            ),
            showlegend=False,
            width=600,
            height=500,
        )

        return fig
