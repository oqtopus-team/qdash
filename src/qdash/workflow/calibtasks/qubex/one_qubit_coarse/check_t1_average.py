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


class CheckT1Average(QubexTask):
    """Task to measure T1 relaxation time multiple times and compute statistics.

    Runs T1 measurement n_runs times, computes mean, std, and CV%,
    and generates a 4-panel fluctuation analysis figure.
    """

    name: str = "CheckT1Average"
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
            value=(np.log10(100), np.log10(500 * 1000), 51),
            description="Time range for T1 time",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for T1 time",
        ),
        "interval": RunParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for T1 time",
        ),
        "n_runs": RunParameterModel(
            unit="",
            value_type="int",
            value=10,
            description="Number of T1 measurement repetitions",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "t1_average": ParameterModel(unit="μs", description="Mean T1 time"),
        "t1_std": ParameterModel(unit="μs", description="T1 standard deviation"),
    }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        label = labels[0]

        n_runs = int(self.run_parameters["n_runs"].get_value())

        t1_values = []
        t1_err_values = []
        r2_values = []
        results = []

        for i in range(n_runs):
            result = exp.t1_experiment(
                time_range=self.run_parameters["time_range"].get_value(),
                shots=self.run_parameters["shots"].get_value(),
                interval=self.run_parameters["interval"].get_value(),
                targets=labels,
            )
            t1_values.append(result.data[label].t1 * 0.001)  # convert to μs
            t1_err_values.append(result.data[label].t1_err * 0.001)
            r2_values.append(result.data[label].r2)
            results.append(result)

        self.save_calibration(backend)

        r2_avg = float(np.mean(r2_values))
        return RunResult(
            raw_result={
                "t1_values": t1_values,
                "t1_err_values": t1_err_values,
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

        t1_values = np.array(result["t1_values"])
        t1_err_values = np.array(result["t1_err_values"])
        r2_values = np.array(result["r2_values"])
        results = result["results"]
        label = result["label"]

        t1_mean = float(np.mean(t1_values))
        t1_std = float(np.std(t1_values, ddof=1)) if len(t1_values) > 1 else 0.0

        self.output_parameters["t1_average"].value = t1_mean
        self.output_parameters["t1_average"].error = t1_std
        self.output_parameters["t1_std"].value = t1_std

        output_parameters = self.attach_execution_id(execution_id)

        fluctuation_fig = self._make_fluctuation_figure(t1_values, t1_err_values, r2_values, qid)
        figures = [fluctuation_fig]
        for r in results:
            figures.append(r.data[label].fit()["fig"])

        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def _make_fluctuation_figure(
        self,
        t1_values: npt.NDArray[np.floating[Any]],
        t1_err_values: npt.NDArray[np.floating[Any]],
        r2_values: npt.NDArray[np.floating[Any]],
        qid: str,
    ) -> go.Figure:
        """Create a 4-panel fluctuation analysis figure."""
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "T1 Time Series",
                "Relative Fluctuation (%)",
                "T1 Histogram",
                "R² per Run",
            ),
        )

        runs = np.arange(1, len(t1_values) + 1)
        t1_mean = float(np.mean(t1_values))

        # Panel 1: T1 time series with error bars, mean line, rolling mean
        fig.add_trace(
            go.Scatter(
                x=runs,
                y=t1_values,
                error_y={"type": "data", "array": t1_err_values, "visible": True},
                mode="markers+lines",
                name="T1",
                marker={"size": 6},
            ),
            row=1,
            col=1,
        )
        fig.add_hline(
            y=t1_mean,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Mean: {t1_mean:.1f} μs",
            row=1,
            col=1,
        )

        # Panel 2: Relative fluctuation from mean (%)
        rel_fluct = (t1_values - t1_mean) / t1_mean * 100
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

        # Panel 3: T1 histogram
        fig.add_trace(
            go.Histogram(
                x=t1_values,
                name="T1 Distribution",
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

        t1_std = float(np.std(t1_values, ddof=1)) if len(t1_values) > 1 else 0.0
        t1_cv = (t1_std / t1_mean * 100) if t1_mean > 0 else 0.0
        fig.update_layout(
            title_text=(
                f"T1 Fluctuation - {qid} "
                f"(Mean: {t1_mean:.1f}, Std: {t1_std:.1f}, CV: {t1_cv:.1f}%)"
            ),
            showlegend=False,
            width=600,
            height=500,
        )

        return fig
