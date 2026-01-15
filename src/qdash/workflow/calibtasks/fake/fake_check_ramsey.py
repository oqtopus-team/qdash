"""Fake CheckRamsey task for testing provenance without real hardware."""

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


class FakeCheckRamsey(FakeTask):
    """Fake task to simulate Ramsey fringe measurement.

    Ramsey experiment measures T2* (dephasing time) and refines qubit frequency.
    This task takes the initial qubit_frequency from ChevronPattern and outputs
    a more precise qubit_frequency along with t2_star.

    Note: Uses same name as qubex task for seamless backend switching.

    Inputs:
        qubit_frequency: Initial qubit frequency from ChevronPattern (GHz)
        hpi_amplitude: Half-pi pulse amplitude from CheckHPI

    Outputs:
        qubit_frequency: Refined qubit frequency from Ramsey measurement (GHz)
        t2_star: T2* dephasing time (μs)
        ramsey_frequency: Detuning frequency observed in Ramsey fringes (MHz)
    """

    name: str = "CheckRamsey"  # Same name as qubex task for backend-agnostic workflows
    task_type: str = "qubit"
    timeout: int = 120

    input_parameters: ClassVar[dict[str, ParameterModel | None]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz",
            description="Initial qubit frequency from ChevronPattern",
        ),
        "hpi_amplitude": ParameterModel(
            unit="a.u.",
            description="Half-pi pulse amplitude from CheckHPI",
        ),
    }

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "time_range": RunParameterModel(
            unit="ns",
            value_type="np.linspace",
            value=(0, 10000, 101),  # 0 to 10 μs
            description="Time range for Ramsey measurement",
        ),
        "artificial_detuning": RunParameterModel(
            unit="MHz",
            value_type="float",
            value=1.0,
            description="Artificial detuning for Ramsey fringes",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=1024,
            description="Number of shots",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz",
            description="Refined qubit frequency from Ramsey measurement",
        ),
        "t2_star": ParameterModel(
            unit="μs",
            description="T2* dephasing time (without echo)",
        ),
        "ramsey_frequency": ParameterModel(
            unit="MHz",
            description="Observed detuning frequency in Ramsey fringes",
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess - loads qubit_frequency from DB."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running a Ramsey fringe experiment.

        The Ramsey experiment measures:
        1. T2* (dephasing time without echo)
        2. Precise qubit frequency (by measuring detuning)

        The output qubit_frequency is refined based on the measured detuning.
        """
        # Get input qubit frequency
        input_freq = None
        qubit_freq_param = self.input_parameters.get("qubit_frequency")
        if qubit_freq_param is not None:
            input_freq = qubit_freq_param.value

        # Generate base values from qubit ID for reproducibility
        qid_int = int(qid) if qid.isdigit() else hash(qid) % 64

        # Simulate T2* value (typically 20-60 μs, shorter than T2 echo)
        t2_star = 30 + (qid_int % 15) * 2 + np.random.normal(0, 3)
        t2_star = max(10, min(80, t2_star))  # Clamp to realistic range

        # Simulate frequency detuning (small correction to input frequency)
        # In real experiments, this comes from fitting the Ramsey fringes
        artificial_detuning = 1.0  # MHz (from run_parameters)
        measured_detuning = artificial_detuning + np.random.normal(0, 0.05)

        # Calculate refined qubit frequency
        # The detuning tells us how far off our drive frequency was
        frequency_correction = np.random.normal(0, 0.001)  # Small correction in GHz
        if input_freq is not None:
            refined_frequency = input_freq + frequency_correction
        else:
            # Default if no input frequency
            refined_frequency = 5.0 + (qid_int % 10) * 0.1 + frequency_correction

        # Generate fake Ramsey fringe data
        time = np.linspace(0, 10000, 101)  # 0 to 10 μs in ns
        omega = 2 * np.pi * measured_detuning / 1000  # Convert MHz to GHz for ns time

        # Ramsey signal: oscillating decay
        # Signal = 0.5 * (1 + cos(ω*t) * exp(-t/T2*))
        decay = np.exp(-time / (t2_star * 1000))  # Convert μs to ns
        oscillation = np.cos(omega * time)
        signal = 0.5 * (1 + oscillation * decay)
        signal += np.random.normal(0, 0.02, len(time))  # Add noise
        signal = np.clip(signal, 0, 1)

        return RunResult(
            raw_result={
                "qubit_frequency": refined_frequency,
                "t2_star": t2_star,
                "ramsey_frequency": measured_detuning,
                "input_frequency": input_freq,
                "frequency_correction": frequency_correction,
                "time": time,
                "signal": signal,
            },
            r2={qid: 0.92 + np.random.uniform(0, 0.06)},
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values with errors
        self.output_parameters["qubit_frequency"].value = result["qubit_frequency"]
        self.output_parameters["qubit_frequency"].error = 0.0001  # 100 kHz precision
        self.output_parameters["t2_star"].value = result["t2_star"]
        self.output_parameters["t2_star"].error = result["t2_star"] * 0.1  # 10% error
        self.output_parameters["ramsey_frequency"].value = result["ramsey_frequency"]
        self.output_parameters["ramsey_frequency"].error = 0.01  # 10 kHz precision

        output_parameters = self.attach_execution_id(execution_id)

        # Generate a figure showing Ramsey fringes
        fig = go.Figure()

        # Data points
        fig.add_trace(
            go.Scatter(
                x=result["time"] / 1000,  # Convert to μs
                y=result["signal"],
                mode="markers",
                name="Data",
                marker={"size": 5, "color": "blue"},
            )
        )

        # Fit curve
        t2_star_ns = result["t2_star"] * 1000
        omega = 2 * np.pi * result["ramsey_frequency"] / 1000
        decay_fit = np.exp(-result["time"] / t2_star_ns)
        fit_signal = 0.5 * (1 + np.cos(omega * result["time"]) * decay_fit)

        fig.add_trace(
            go.Scatter(
                x=result["time"] / 1000,
                y=fit_signal,
                mode="lines",
                name=f"Fit (T2* = {result['t2_star']:.1f} μs)",
                line={"color": "red", "width": 2},
            )
        )

        # Add envelope
        upper_envelope = 0.5 * (1 + decay_fit)
        lower_envelope = 0.5 * (1 - decay_fit)
        fig.add_trace(
            go.Scatter(
                x=result["time"] / 1000,
                y=upper_envelope,
                mode="lines",
                name="Envelope",
                line={"color": "gray", "dash": "dash", "width": 1},
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=result["time"] / 1000,
                y=lower_envelope,
                mode="lines",
                line={"color": "gray", "dash": "dash", "width": 1},
                showlegend=False,
            )
        )

        fig.update_layout(
            title=f"Ramsey Fringes - {qid}",
            xaxis_title="Time (μs)",
            yaxis_title="Population",
            legend={"x": 0.7, "y": 0.95},
        )

        # Add annotation with results
        annotation_text = (
            (
                f"Input freq: {result['input_frequency']:.6f} GHz<br>"
                f"Refined freq: {result['qubit_frequency']:.6f} GHz<br>"
                f"T2* = {result['t2_star']:.1f} μs"
            )
            if result["input_frequency"]
            else (
                f"Refined freq: {result['qubit_frequency']:.6f} GHz<br>"
                f"T2* = {result['t2_star']:.1f} μs"
            )
        )
        fig.add_annotation(
            x=0.02,
            y=0.02,
            xref="paper",
            yref="paper",
            text=annotation_text,
            showarrow=False,
            font={"size": 10},
            align="left",
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="gray",
            borderwidth=1,
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
        )
