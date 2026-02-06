"""Fake CheckRabi task for testing provenance without real hardware."""

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


class FakeCheckRabi(FakeTask):
    """Fake task to simulate Rabi oscillation measurement.

    This task depends on qubit_frequency from ChevronPattern.
    It simulates measuring Rabi oscillations to determine control parameters.

    Note: Uses same name as qubex task for seamless backend switching.

    Inputs:
        qubit_frequency: From ChevronPattern (loaded from DB)

    Outputs:
        rabi_amplitude: Rabi oscillation amplitude
        rabi_frequency: Rabi oscillation frequency (MHz)
        rabi_phase: Rabi oscillation phase
        rabi_offset: Rabi oscillation offset
    """

    name: str = "CheckRabi"  # Same name as qubex task for backend-agnostic workflows
    task_type: str = "qubit"
    timeout: int = 60

    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz",
            description="Qubit frequency from ChevronPattern",
        ),
    }

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 401, 8),
            description="Time range for Rabi oscillation",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=1024,
            description="Number of shots",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "rabi_amplitude": ParameterModel(
            unit="a.u.",
            description="Rabi oscillation amplitude",
        ),
        "rabi_frequency": ParameterModel(
            unit="MHz",
            description="Rabi oscillation frequency",
        ),
        "rabi_phase": ParameterModel(
            unit="rad",
            description="Rabi oscillation phase",
        ),
        "rabi_offset": ParameterModel(
            unit="a.u.",
            description="Rabi oscillation offset",
        ),
        "maximum_rabi_frequency": ParameterModel(
            unit="MHz/a.u.",
            description="Maximum Rabi frequency per unit control amplitude",
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess - loads qubit_frequency from DB."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running a Rabi oscillation experiment.

        The results depend on the input qubit_frequency for realistic behavior.
        """
        # Get input parameter (may be loaded from DB or None)
        qubit_freq = None
        qubit_freq_param = self.input_parameters.get("qubit_frequency")
        if qubit_freq_param is not None:
            qubit_freq = qubit_freq_param.value

        # Base Rabi frequency depends on qubit frequency (realistic coupling)
        if qubit_freq:
            base_rabi_freq = 10.0 + (qubit_freq - 5.0) * 2.0  # MHz
        else:
            base_rabi_freq = 12.0  # Default

        # Simulate Rabi parameters with realistic noise
        rabi_frequency = base_rabi_freq + np.random.normal(0, 0.5)
        rabi_amplitude = 0.45 + np.random.normal(0, 0.02)
        rabi_phase = np.random.uniform(-0.1, 0.1)
        rabi_offset = 0.5 + np.random.normal(0, 0.01)

        # Generate fake Rabi oscillation data
        time = np.arange(0, 401, 8)
        omega = 2 * np.pi * rabi_frequency / 1000  # Convert to GHz
        signal = rabi_offset + rabi_amplitude * np.cos(omega * time + rabi_phase)
        signal += np.random.normal(0, 0.03, len(time))  # Add noise

        return RunResult(
            raw_result={
                "rabi_amplitude": rabi_amplitude,
                "rabi_frequency": rabi_frequency,
                "rabi_phase": rabi_phase,
                "rabi_offset": rabi_offset,
                "time": time,
                "signal": signal,
            },
            r2={qid: 0.95 + np.random.uniform(0, 0.04)},  # Simulated R² value
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values with errors
        self.output_parameters["rabi_amplitude"].value = result["rabi_amplitude"]
        self.output_parameters["rabi_amplitude"].error = 0.005
        self.output_parameters["rabi_frequency"].value = result["rabi_frequency"]
        self.output_parameters["rabi_frequency"].error = 0.1
        self.output_parameters["rabi_phase"].value = result["rabi_phase"]
        self.output_parameters["rabi_phase"].error = 0.01
        self.output_parameters["rabi_offset"].value = result["rabi_offset"]
        self.output_parameters["rabi_offset"].error = 0.005

        # Maximum Rabi frequency = rabi_frequency / control_amplitude
        fake_control_amplitude = 0.0125  # Default control amplitude for fake backend
        self.output_parameters["maximum_rabi_frequency"].value = (
            result["rabi_frequency"] / fake_control_amplitude
        )

        output_parameters = self.attach_execution_id(execution_id)

        # Generate a figure
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=result["time"],
                y=result["signal"],
                mode="markers",
                name="Data",
                marker={"size": 6},
            )
        )

        # Add fit line
        omega = 2 * np.pi * result["rabi_frequency"] / 1000
        fit_signal = result["rabi_offset"] + result["rabi_amplitude"] * np.cos(
            omega * result["time"] + result["rabi_phase"]
        )
        fig.add_trace(
            go.Scatter(
                x=result["time"],
                y=fit_signal,
                mode="lines",
                name="Fit",
                line={"color": "red"},
            )
        )

        fig.update_layout(
            title=f"Rabi Oscillation - {qid}",
            xaxis_title="Time (ns)",
            yaxis_title="Population",
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
            raw_data=[np.column_stack([result["time"], result["signal"]])],
        )
