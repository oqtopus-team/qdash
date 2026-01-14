"""Fake CheckT2Echo task for testing provenance without real hardware."""

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


class FakeCheckT2Echo(FakeTask):
    """Fake task to simulate T2 echo (Hahn echo) measurement.

    This task depends on qubit_frequency and hpi_amplitude.
    It simulates measuring the T2 echo dephasing time.

    Note: Uses same name as qubex task for seamless backend switching.

    Inputs:
        qubit_frequency: From ChevronPattern (loaded from DB)
        hpi_amplitude: From CheckHPI (loaded from DB)

    Outputs:
        t2_echo: T2 echo dephasing time (μs)
    """

    name: str = "CheckT2Echo"  # Same name as qubex task for backend-agnostic workflows
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
            value=(2, 5.5, 51),  # 100 ns to 316 μs
            description="Time range for T2 echo measurement (log scale)",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=1024,
            description="Number of shots",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "t2_echo": ParameterModel(
            unit="μs",
            description="T2 echo (Hahn echo) dephasing time",
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess - loads dependencies from DB."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running a T2 echo measurement."""
        # Generate realistic T2 echo value based on qubit ID
        qid_int = int(qid) if qid.isdigit() else hash(qid) % 64
        t2_echo = 60 + (qid_int % 20) * 2 + np.random.normal(0, 5)
        t2_echo = max(20, min(200, t2_echo))  # Clamp to realistic range

        # Generate fake T2 echo decay data
        time = np.logspace(2, 5.5, 51)  # 100 ns to 316 μs
        decay = np.exp(-time / (t2_echo * 1000))  # Convert μs to ns
        # Add some oscillation (simulating slight detuning)
        oscillation = 0.05 * np.cos(2 * np.pi * time / 50000)
        signal = decay * (1 + oscillation) + np.random.normal(0, 0.02, len(time))
        signal = np.clip(signal, 0, 1)

        return RunResult(
            raw_result={
                "t2_echo": t2_echo,
                "time": time,
                "signal": signal,
            },
            r2={qid: 0.95 + np.random.uniform(0, 0.04)},
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values
        self.output_parameters["t2_echo"].value = result["t2_echo"]
        self.output_parameters["t2_echo"].error = result["t2_echo"] * 0.08  # 8% error

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
        fit_signal = np.exp(-result["time"] / (result["t2_echo"] * 1000))
        fig.add_trace(
            go.Scatter(
                x=result["time"] / 1000,
                y=fit_signal,
                mode="lines",
                name=f"Fit (T2 echo = {result['t2_echo']:.1f} μs)",
                line={"color": "red"},
            )
        )

        fig.update_layout(
            title=f"T2 Echo (Hahn Echo) - {qid}",
            xaxis_title="Time (μs)",
            yaxis_title="Population",
            xaxis_type="log",
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
        )
