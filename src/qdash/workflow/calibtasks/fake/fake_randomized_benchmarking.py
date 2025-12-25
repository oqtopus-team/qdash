"""Fake RandomizedBenchmarking task for testing provenance without real hardware."""

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


class FakeRandomizedBenchmarking(FakeTask):
    """Fake task to simulate Randomized Benchmarking.

    This task depends on multiple previous calibration parameters.
    It simulates measuring gate fidelity through RB.

    Note: Uses same name as qubex task for seamless backend switching.

    Inputs:
        qubit_frequency: From ChevronPattern
        rabi_amplitude: From CheckRabi
        t1: From CheckT1
        t2_echo: From CheckT2Echo

    Outputs:
        gate_fidelity: Average Clifford gate fidelity
        error_per_gate: Error per Clifford gate
    """

    name: str = "RandomizedBenchmarking"  # Same name as qubex task for backend-agnostic workflows
    task_type: str = "qubit"
    timeout: int = 300

    input_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz",
            description="Qubit frequency from ChevronPattern",
        ),
        "rabi_amplitude": ParameterModel(
            unit="",
            description="Rabi amplitude from CheckRabi",
        ),
        "t1": ParameterModel(
            unit="μs",
            description="T1 relaxation time from CheckT1",
        ),
        "t2_echo": ParameterModel(
            unit="μs",
            description="T2 echo dephasing time from CheckT2Echo",
        ),
    }

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "num_cliffords": RunParameterModel(
            unit="",
            value_type="list",
            value=[1, 2, 4, 8, 16, 32, 64, 128, 256],
            description="Number of Clifford gates per sequence",
        ),
        "num_seeds": RunParameterModel(
            unit="",
            value_type="int",
            value=20,
            description="Number of random seeds per Clifford count",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=1024,
            description="Number of shots per circuit",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "gate_fidelity": ParameterModel(
            unit="",
            description="Average Clifford gate fidelity",
        ),
        "error_per_gate": ParameterModel(
            unit="",
            description="Error per Clifford gate (1 - fidelity)",
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess - loads all dependencies from DB."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running Randomized Benchmarking.

        Gate fidelity depends on T1, T2, and calibration quality.
        """
        # Get input parameters
        t1_value = None
        t2_value = None
        rabi_amp = None

        if self.input_parameters.get("t1"):
            t1_value = self.input_parameters["t1"].value
        if self.input_parameters.get("t2_echo"):
            t2_value = self.input_parameters["t2_echo"].value
        if self.input_parameters.get("rabi_amplitude"):
            rabi_amp = self.input_parameters["rabi_amplitude"].value

        # Base fidelity (high quality device)
        base_fidelity = 0.998

        # Fidelity degrades with lower T1/T2 and imperfect Rabi amplitude
        if rabi_amp:
            # Optimal Rabi amplitude is around 0.5, deviation degrades fidelity
            amp_deviation = abs(rabi_amp - 0.5)
            base_fidelity *= (1.0 - amp_deviation * 0.02)  # Small penalty for deviation
        if t1_value:
            t1_factor = min(1.0, t1_value / 100)  # Normalized to 100 μs
            base_fidelity *= (0.95 + 0.05 * t1_factor)
        if t2_value:
            t2_factor = min(1.0, t2_value / 80)  # Normalized to 80 μs
            base_fidelity *= (0.95 + 0.05 * t2_factor)

        # Add some randomness
        gate_fidelity = base_fidelity + np.random.normal(0, 0.001)
        gate_fidelity = min(0.9999, max(0.99, gate_fidelity))
        error_per_gate = 1 - gate_fidelity

        # Generate fake RB data
        num_cliffords = np.array([1, 2, 4, 8, 16, 32, 64, 128, 256])
        # Exponential decay: p = A * fidelity^m + B
        A = 0.5
        B = 0.5
        decay_rate = gate_fidelity
        survival_prob = A * np.power(decay_rate, num_cliffords) + B
        # Add noise
        survival_prob += np.random.normal(0, 0.01, len(num_cliffords))
        survival_prob = np.clip(survival_prob, 0, 1)

        return RunResult(
            raw_result={
                "gate_fidelity": gate_fidelity,
                "error_per_gate": error_per_gate,
                "num_cliffords": num_cliffords,
                "survival_prob": survival_prob,
                "decay_rate": decay_rate,
            },
            r2={qid: 0.98 + np.random.uniform(0, 0.015)},
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values
        self.output_parameters["gate_fidelity"].value = result["gate_fidelity"]
        self.output_parameters["gate_fidelity"].error = 0.0005
        self.output_parameters["error_per_gate"].value = result["error_per_gate"]
        self.output_parameters["error_per_gate"].error = 0.0005

        output_parameters = self.attach_execution_id(execution_id)

        # Generate a figure
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=result["num_cliffords"],
                y=result["survival_prob"],
                mode="markers",
                name="Data",
                marker=dict(size=8),
                error_y=dict(type="constant", value=0.01),
            )
        )

        # Add fit line
        A = 0.5
        B = 0.5
        fit_prob = A * np.power(result["decay_rate"], result["num_cliffords"]) + B
        fig.add_trace(
            go.Scatter(
                x=result["num_cliffords"],
                y=fit_prob,
                mode="lines",
                name=f"Fit (F = {result['gate_fidelity']:.4f})",
                line=dict(color="red"),
            )
        )

        fig.update_layout(
            title=f"Randomized Benchmarking - {qid}",
            xaxis_title="Number of Cliffords",
            yaxis_title="Survival Probability",
            xaxis_type="log",
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
        )
