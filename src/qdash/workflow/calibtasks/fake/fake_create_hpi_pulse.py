"""Fake CheckHPI task for testing provenance without real hardware."""

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


class FakeCreateHPIPulse(FakeTask):
    """Fake task to simulate Half-Pi (HPI) pulse calibration.

    This task depends on qubit_frequency from ChevronPattern.
    It simulates calibrating the half-pi pulse parameters.

    Note: Uses same name as qubex task for seamless backend switching.

    Inputs:
        qubit_frequency: From ChevronPattern (loaded from DB)

    Outputs:
        hpi_amplitude: Half-pi pulse amplitude
        hpi_length: Half-pi pulse duration (ns)
    """

    name: str = "CreateHPIPulse"  # Same name as qubex task for backend-agnostic workflows
    task_type: str = "qubit"
    timeout: int = 60

    input_parameters: ClassVar[dict[str, ParameterModel]] = {
        "qubit_frequency": ParameterModel(
            unit="GHz",
            description="Qubit frequency from ChevronPattern",
        ),
    }

    run_parameters: ClassVar[dict[str, RunParameterModel]] = {
        "amplitude_range": RunParameterModel(
            unit="a.u.",
            value_type="range",
            value=(0.1, 0.5, 21),
            description="Amplitude range for HPI calibration",
        ),
        "duration": RunParameterModel(
            unit="ns",
            value_type="int",
            value=20,
            description="HPI pulse duration",
        ),
        "shots": RunParameterModel(
            unit="",
            value_type="int",
            value=1024,
            description="Number of shots",
        ),
    }

    output_parameters: ClassVar[dict[str, ParameterModel]] = {
        "hpi_amplitude": ParameterModel(
            unit="a.u.",
            description="Half-pi pulse amplitude",
        ),
        "hpi_length": ParameterModel(
            unit="ns",
            description="Half-pi pulse duration",
        ),
    }

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess - loads qubit_frequency from DB."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Simulate running an HPI pulse calibration experiment.

        The HPI amplitude depends on the qubit frequency.
        """
        # Get input parameter
        qubit_freq = None
        if self.input_parameters.get("qubit_frequency"):
            qubit_freq = self.input_parameters["qubit_frequency"].value

        # Simulate HPI amplitude (typically 0.2-0.4)
        # Higher frequency qubits may need slightly different amplitudes
        qid_int = int(qid) if qid.isdigit() else hash(qid) % 64
        base_amplitude = 0.25 + (qid_int % 10) * 0.01  # 0.25-0.34 base

        if qubit_freq:
            # Slight correlation with frequency
            base_amplitude += (qubit_freq - 5.0) * 0.02

        hpi_amplitude = base_amplitude + np.random.normal(0, 0.01)
        hpi_amplitude = max(0.15, min(0.45, hpi_amplitude))  # Clamp

        # HPI length is typically fixed but can vary slightly
        hpi_length = 20 + np.random.randint(-2, 3)  # 18-22 ns

        # Generate fake calibration data (Rabi-like oscillation)
        amplitudes = np.linspace(0.1, 0.5, 21)
        # HPI should give 0.5 probability (halfway rotation)
        signal = 0.5 * (1 - np.cos(np.pi * amplitudes / hpi_amplitude))
        signal += np.random.normal(0, 0.02, len(amplitudes))
        signal = np.clip(signal, 0, 1)

        return RunResult(
            raw_result={
                "hpi_amplitude": hpi_amplitude,
                "hpi_length": hpi_length,
                "amplitudes": amplitudes,
                "signal": signal,
            },
            r2={qid: 0.96 + np.random.uniform(0, 0.03)},
        )

    def postprocess(
        self, backend: FakeBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Process results and generate output parameters."""
        result = run_result.raw_result

        # Set output parameter values
        self.output_parameters["hpi_amplitude"].value = result["hpi_amplitude"]
        self.output_parameters["hpi_amplitude"].error = 0.005
        self.output_parameters["hpi_length"].value = result["hpi_length"]
        self.output_parameters["hpi_length"].error = 1.0

        output_parameters = self.attach_execution_id(execution_id)

        # Generate a figure
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=result["amplitudes"],
                y=result["signal"],
                mode="markers",
                name="Data",
                marker=dict(size=6),
            )
        )

        # Add fit line
        fit_signal = 0.5 * (1 - np.cos(np.pi * result["amplitudes"] / result["hpi_amplitude"]))
        fig.add_trace(
            go.Scatter(
                x=result["amplitudes"],
                y=fit_signal,
                mode="lines",
                name=f"Fit (amp = {result['hpi_amplitude']:.3f})",
                line=dict(color="red"),
            )
        )

        # Mark the HPI amplitude
        fig.add_vline(
            x=result["hpi_amplitude"],
            line_dash="dash",
            line_color="green",
            annotation_text=f"HPI = {result['hpi_amplitude']:.3f}",
        )

        fig.update_layout(
            title=f"HPI Pulse Calibration - {qid}",
            xaxis_title="Amplitude (a.u.)",
            yaxis_title="Population",
        )

        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[fig],
        )
