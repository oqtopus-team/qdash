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

    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {}

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "frequency_range": RunParameterModel(
            unit="GHz",
            value_type="range",
            value=(7.82, 7.94, 101),
            description="Drive frequency range for chevron pattern",
        ),
        "time_range": RunParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 200, 51),
            description="Time range for chevron pattern",
        ),
        "control_amplitude": RunParameterModel(
            unit="a.u.",
            value_type="float",
            value=0.5,
            description="Control pulse amplitude",
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

        Generates realistic-looking simulated data with characteristic V-shape.
        """
        # Base frequency depends on qubit ID for realistic variation
        qid_int = int(qid) if qid.isdigit() else hash(qid) % 64

        # Qubit frequency in the 7.84-7.92 GHz range (matches readout freq range)
        center_freq = 7.86 + (qid_int % 10) * 0.006  # 7.86-7.92 GHz range
        qubit_frequency = center_freq + np.random.normal(0, 0.001)

        # Readout frequency slightly above qubit frequency
        readout_frequency = qubit_frequency + 0.3 + np.random.normal(0, 0.002)

        # Generate chevron pattern data
        frequencies = np.linspace(7.82, 7.94, 101)
        times = np.linspace(0, 200, 51)
        F, T = np.meshgrid(frequencies, times)

        # Detuning from qubit frequency
        detuning = F - qubit_frequency

        # Generalized Rabi frequency: sqrt(detuning^2 + Omega^2)
        omega_drive = 0.025  # Rabi frequency at resonance (GHz)
        omega_gen = np.sqrt(detuning**2 + omega_drive**2)

        # Chevron pattern: Rabi oscillations that spread out with detuning
        # Signal oscillates faster off-resonance (V-shape in time vs frequency)
        # The pattern shows cos oscillation with envelope decay
        decay_rate = 0.005  # Decay per ns
        oscillation = np.cos(2 * np.pi * omega_gen * T)
        envelope = np.exp(-decay_rate * T)

        # Pattern ranges from -1 to 1 like in the sample image
        pattern = oscillation * envelope

        # Add realistic noise
        pattern += np.random.normal(0, 0.05, pattern.shape)
        pattern = np.clip(pattern, -1, 1)

        return RunResult(
            raw_result={
                "qubit_frequency": qubit_frequency,
                "readout_frequency": readout_frequency,
                "pattern": pattern,
                "frequencies": frequencies,
                "times": times,
            }
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values
        self.output_parameters["qubit_frequency"].value = result["qubit_frequency"]
        self.output_parameters["qubit_frequency"].error = 0.001
        self.output_parameters["readout_frequency"].value = result["readout_frequency"]
        self.output_parameters["readout_frequency"].error = 0.002

        output_parameters = self.attach_execution_id(execution_id)

        # Generate a figure matching the sample image format
        # X-axis: Drive frequency (GHz), Y-axis: Time (ns)
        fig = go.Figure(
            data=go.Heatmap(
                z=result["pattern"],  # Shape: (times, frequencies)
                x=result["frequencies"],
                y=result["times"],
                colorscale="Viridis",
                zmin=-1,
                zmax=1,
                colorbar={
                    "title": "",
                    "tickvals": [-1, -0.5, 0, 0.5, 1],
                },
            )
        )
        fig.update_layout(
            title={
                "text": f"Chevron pattern : Q{qid}<br><sub>control_amplitude=</sub>",
                "x": 0.5,
                "xanchor": "center",
            },
            xaxis_title="Drive frequency (GHz)",
            yaxis_title="Time (ns)",
            width=600,
            height=500,
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
        )
