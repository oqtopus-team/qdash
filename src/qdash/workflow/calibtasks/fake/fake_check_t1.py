"""Fake CheckT1 task for testing provenance without real hardware."""

from typing import ClassVar

import numpy as np
import plotly.graph_objects as go
from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.fake.base import FakeTask
from qdash.workflow.engine.backend.fake import FakeBackend


class FakeCheckT1(FakeTask):
    """Fake task to simulate T1 relaxation time measurement.

    This task depends on qubit_frequency and hpi_amplitude.
    It simulates measuring the T1 relaxation time.

    Note: Uses same name as qubex task for seamless backend switching.

    Inputs:
        qubit_frequency: From ChevronPattern (loaded from DB)
        hpi_amplitude: From CheckHPI (loaded from DB)

    Outputs:
        t1: T1 relaxation time (μs)
    """

    name: str = "CheckT1"  # Same name as qubex task for backend-agnostic workflows
    task_type: str = "qubit"
    timeout: int = 120

    input_parameters: ClassVar[dict[str, ParameterModel]] = {
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
            value=(2, 5.7, 51),  # 100 ns to 500 μs
            description="Time range for T1 measurement (log scale)",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=1024,
            description="Number of shots",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "t1": ParameterModel(
            unit="μs",
            description="T1 relaxation time",
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess - loads qubit_frequency from DB."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running a T1 measurement experiment.

        The T1 value has some correlation with qubit frequency.
        """
        # Get input parameter
        qubit_freq = None
        if self.input_parameters.get("qubit_frequency"):
            qubit_freq = self.input_parameters["qubit_frequency"].value

        # Simulate T1 value (typically 50-150 μs for transmons)
        # Higher frequency qubits tend to have slightly lower T1
        qid_int = int(qid) if qid.isdigit() else hash(qid) % 64
        base_t1 = 80 + (qid_int % 20) * 3  # 80-137 μs base

        if qubit_freq:
            # Slight negative correlation with frequency
            base_t1 -= (qubit_freq - 5.0) * 5

        t1 = base_t1 + np.random.normal(0, 5)  # Add variability
        t1 = max(30, min(200, t1))  # Clamp to realistic range

        # Generate fake T1 decay data
        time = np.logspace(2, 5.7, 51)  # 100 ns to 500 μs
        decay = np.exp(-time / (t1 * 1000))  # Convert μs to ns
        signal = decay + np.random.normal(0, 0.02, len(time))
        signal = np.clip(signal, 0, 1)

        return RunResult(
            raw_result={
                "t1": t1,
                "time": time,
                "signal": signal,
            },
            r2={qid: 0.97 + np.random.uniform(0, 0.02)},
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values
        self.output_parameters["t1"].value = result["t1"]
        self.output_parameters["t1"].error = result["t1"] * 0.05  # 5% error

        output_parameters = self.attach_execution_id(execution_id)

        # Generate a figure
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=result["time"] / 1000,  # Convert to μs
                y=result["signal"],
                mode="markers",
                name="Data",
                marker={"size": 6},
            )
        )

        # Add fit line
        fit_signal = np.exp(-result["time"] / (result["t1"] * 1000))
        fig.add_trace(
            go.Scatter(
                x=result["time"] / 1000,
                y=fit_signal,
                mode="lines",
                name=f"Fit (T1 = {result['t1']:.1f} μs)",
                line={"color": "red"},
            )
        )

        fig.update_layout(
            title=f"T1 Relaxation - {qid}",
            xaxis_title="Time (μs)",
            yaxis_title="Population",
            xaxis_type="log",
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
        )
