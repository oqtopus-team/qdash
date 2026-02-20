"""Fake CheckT2EchoAverage task for testing provenance without real hardware."""

from typing import Any, ClassVar

import numpy as np
import numpy.typing as npt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.fake.base import FakeTask
from qdash.workflow.engine.backend.fake import FakeBackend


class FakeCheckT2EchoAverage(FakeTask):
    """Fake task to simulate repeated T2 echo measurement.

    This task depends on qubit_frequency and hpi_amplitude.
    It simulates measuring T2 echo time n_runs times and computing statistics.

    Note: Uses same name as qubex task for seamless backend switching.

    Inputs:
        qubit_frequency: From ChevronPattern (loaded from DB)
        hpi_amplitude: From CheckHPI (loaded from DB)

    Outputs:
        t2_echo_average: Mean T2 echo time (μs)
        t2_echo_std: T2 echo standard deviation (μs)
    """

    name: str = "CheckT2EchoAverage"  # Same name as qubex task for backend-agnostic workflows
    task_type: str = "qubit"
    timeout: int = 120

    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz",
            description="Qubit frequency from ChevronPattern",
        ),
        "hpi_amplitude": ParameterModel(
            unit="a.u.",
            description="Half-pi pulse amplitude from CheckHPI",
        ),
    }

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="np.logspace",
            value=(2, 5.5, 51),  # 100 ns to 316 μs
            description="Time range for T2 echo measurement (log scale)",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=1024,
            description="Number of shots",
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

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess - loads qubit_frequency from DB."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running repeated T2 echo measurement experiments."""
        qubit_freq = None
        qubit_freq_param = self.input_parameters.get("qubit_frequency")
        if qubit_freq_param is not None:
            qubit_freq = qubit_freq_param.value

        # Base T2 echo derived from qid (matching FakeCheckT2Echo physics logic)
        qid_int = int(qid) if qid.isdigit() else hash(qid) % 64
        base_t2: float = 60 + (qid_int % 20) * 2  # 60-98 μs base

        if qubit_freq:
            base_t2 -= (qubit_freq - 5.0) * 3

        n_runs = int(self.run_parameters["n_runs"].get_value())

        t2_values = []
        t2_err_values = []
        r2_values = []
        time_arrays = []
        signal_arrays = []

        for _ in range(n_runs):
            t2 = base_t2 + np.random.normal(0, 5)  # Add variability
            t2 = max(20, min(200, t2))  # Clamp to realistic range
            t2_err = t2 * 0.08  # 8% error per measurement

            # Generate fake T2 echo decay data
            time_arr = np.logspace(2, 5.5, 51)  # 100 ns to 316 μs
            decay = np.exp(-time_arr / (t2 * 1000))  # Convert μs to ns
            oscillation = 0.05 * np.cos(2 * np.pi * time_arr / 50000)
            signal = decay * (1 + oscillation) + np.random.normal(0, 0.02, len(time_arr))
            signal = np.clip(signal, 0, 1)

            r2 = 0.95 + np.random.uniform(0, 0.04)

            t2_values.append(t2)
            t2_err_values.append(t2_err)
            r2_values.append(r2)
            time_arrays.append(time_arr)
            signal_arrays.append(signal)

        r2_avg = float(np.mean(r2_values))

        return RunResult(
            raw_result={
                "t2_values": t2_values,
                "t2_err_values": t2_err_values,
                "r2_values": r2_values,
                "time_arrays": time_arrays,
                "signal_arrays": signal_arrays,
            },
            r2={qid: r2_avg},
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        t2_values = np.array(result["t2_values"])
        t2_err_values = np.array(result["t2_err_values"])
        r2_values = np.array(result["r2_values"])

        t2_mean = float(np.mean(t2_values))
        t2_std = float(np.std(t2_values, ddof=1)) if len(t2_values) > 1 else 0.0

        self.output_parameters["t2_echo_average"].value = t2_mean
        self.output_parameters["t2_echo_average"].error = t2_std
        self.output_parameters["t2_echo_std"].value = t2_std

        output_parameters = self.attach_execution_id(execution_id)

        fluctuation_fig = self._make_fluctuation_figure(t2_values, t2_err_values, r2_values, qid)

        # Generate fit figures for all runs
        figures = [fluctuation_fig]
        for i in range(len(t2_values)):
            time_arr = np.array(result["time_arrays"][i])
            signal_arr = np.array(result["signal_arrays"][i])
            figures.append(self._make_fit_figure(time_arr, signal_arr, t2_values[i], qid, i + 1))

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=figures,
        )

    def _make_fit_figure(
        self,
        time: npt.NDArray[np.floating[Any]],
        signal: npt.NDArray[np.floating[Any]],
        t2: float,
        qid: str,
        run_num: int = 1,
    ) -> go.Figure:
        """Create a fit figure for a T2 echo measurement run."""
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=time / 1000,
                y=signal,
                mode="markers",
                name="Data",
                marker={"size": 6},
            )
        )
        fit_signal = np.exp(-time / (t2 * 1000))
        fig.add_trace(
            go.Scatter(
                x=time / 1000,
                y=fit_signal,
                mode="lines",
                name=f"Fit (T2 echo = {t2:.1f} μs)",
                line={"color": "red"},
            )
        )
        fig.update_layout(
            title=f"T2 Echo (Run #{run_num}) - {qid}",
            xaxis_title="Time (μs)",
            yaxis_title="Population",
            xaxis_type="log",
        )
        return fig

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
