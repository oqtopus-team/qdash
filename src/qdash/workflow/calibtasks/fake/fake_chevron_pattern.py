"""Fake ChevronPattern task for testing provenance without real hardware."""

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


class FakeChevronPattern(FakeTask):
    """Fake task to simulate chevron pattern calibration.

    This is the entry point task that determines the qubit frequency.
    It simulates finding the resonant frequency through a chevron pattern sweep.

    Note: Uses same name as qubex task for seamless backend switching.

    Outputs:
        qubit_frequency: Simulated qubit bare frequency (GHz)
        readout_frequency: Simulated readout resonator frequency (GHz)
    """

    name: str = "ChevronPattern"  # Same name as qubex task for backend-agnostic workflows
    task_type: str = "qubit"
    timeout: int = 60

    input_parameters: ClassVar[dict[str, ParameterModel]] = {}

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "detuning_range": RunParameterModel(
            unit="GHz",
            value_type="range",
            value=(-0.05, 0.05, 51),
            description="Detuning range for chevron pattern",
        ),
        "time_range": RunParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 201, 4),
            description="Time range for chevron pattern",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz",
            description="Qubit bare frequency determined from chevron pattern",
        ),
        "readout_frequency": ParameterModel(
            unit="GHz",
            description="Readout resonator frequency",
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess the task - no input dependencies for ChevronPattern."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running a chevron pattern experiment.

        Generates realistic-looking simulated data with some randomness.
        """
        # Base frequency depends on qubit ID for realistic variation
        qid_int = int(qid) if qid.isdigit() else hash(qid) % 64
        base_qubit_freq = 5.0 + (qid_int % 10) * 0.1  # 5.0-5.9 GHz range
        base_readout_freq = 7.0 + (qid_int % 10) * 0.05  # 7.0-7.45 GHz range

        # Add some noise to simulate real measurements
        qubit_frequency = base_qubit_freq + np.random.normal(0, 0.005)
        readout_frequency = base_readout_freq + np.random.normal(0, 0.002)

        # Generate fake chevron pattern data for visualization
        detuning = np.linspace(-0.05, 0.05, 51)
        time = np.arange(0, 201, 4)
        T, D = np.meshgrid(time, detuning)

        # Simulate chevron pattern: oscillation that depends on detuning
        omega = 2 * np.pi * 0.01  # Rabi frequency
        pattern = 0.5 * (1 - np.cos(omega * T) * np.exp(-np.abs(D) * 50))
        pattern += np.random.normal(0, 0.02, pattern.shape)  # Add noise

        return RunResult(
            raw_result={
                "qubit_frequency": qubit_frequency,
                "readout_frequency": readout_frequency,
                "pattern": pattern,
                "detuning": detuning,
                "time": time,
            }
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values
        self.output_parameters["qubit_frequency"].value = result["qubit_frequency"]
        self.output_parameters["readout_frequency"].value = result["readout_frequency"]

        output_parameters = self.attach_execution_id(execution_id)

        # Generate a figure
        fig = go.Figure(
            data=go.Heatmap(
                z=result["pattern"],
                x=result["time"],
                y=result["detuning"] * 1000,  # Convert to MHz
                colorscale="RdBu",
            )
        )
        fig.update_layout(
            title=f"Chevron Pattern - {qid}",
            xaxis_title="Time (ns)",
            yaxis_title="Detuning (MHz)",
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
        )
