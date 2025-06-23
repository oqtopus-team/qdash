from collections import defaultdict
from typing import ClassVar

import numpy as np
import numpy.typing as npt
import plotly.graph_objects as go
import qubex as qx
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.calibration.util import qid_to_label
from qdash.workflow.core.session.fake import FakeSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS
from qubex.simulator import Control, QuantumSimulator, QuantumSystem, SimulationResult, Transmon


def downsample(
    data: npt.NDArray,
    n_samples: int | None,
) -> npt.NDArray:
    if n_samples is None:
        return data
    if len(data) <= n_samples:
        return data
    indices = np.linspace(0, len(data) - 1, n_samples).astype(int)
    return data[indices]


class CustomSimulationResult(SimulationResult):
    """Custom simulation result to handle Rabi parameters."""

    def __init__(self, **kwargs):
        """Initialize the custom simulation result."""
        super().__init__(**kwargs)

    def plot_population_dynamics(self, label=None, *, n_samples=None):
        """Plot the population dynamics of the states.

        Parameters
        ----------
        label : Optional[str], optional
            The label of the qubit, by default

        """
        states = self.states if label is None else self.get_substates(label)
        populations = defaultdict(list)
        for state in states:
            population = np.abs(state.diag())
            population[population > 1] = 1.0
            for idx, prob in enumerate(population):
                basis = self.system.basis_labels[idx] if label is None else str(idx)
                populations[f"|{basis}〉"].append(prob)

        sampled_times = self.get_times(n_samples=n_samples)
        sampled_populations = {
            key: downsample(np.asarray(value), n_samples) for key, value in populations.items()
        }

        fig = go.Figure()
        for key, value in sampled_populations.items():
            fig.add_trace(
                go.Scatter(
                    x=sampled_times,
                    y=value,
                    mode="lines",
                    name=key,
                )
            )
        fig.update_layout(
            title="Population dynamics" if label is None else f"Population dynamics : {label}",
            xaxis_title="Time (ns)",
            yaxis_title="Population",
        )
        fig.show()
        return fig


class FakeRabi(BaseTask):
    """Task to check the Fake Rabi oscillation."""

    name: str = "FakeRabi"
    backend: str = "fake"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "time_range": InputParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 201, 4),
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: FakeSession, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result

        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.plot_population_dynamics()]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, session: FakeSession, qid: str) -> RunResult:
        """Run the task."""
        label = qid_to_label(qid)
        qubit = Transmon(
            label=label,
            dimension=2,
            frequency=7.648,
            anharmonicity=-0.333,
            relaxation_rate=0.00005,
            dephasing_rate=0.00005,
        )
        # Define the quantum system with the qubit
        system = QuantumSystem(objects=[qubit])

        # Define the quantum simulator with the system
        simulator = QuantumSimulator(system)
        duration = 100
        drive = qx.pulse.Rect(
            duration=duration,
            amplitude=2 * (2 * np.pi) / duration,
        )
        control = Control(
            target=qubit,
            waveform=drive,
        )
        result = simulator.mesolve(
            controls=[control],  # List of controls
            initial_state={label: "0"},  # Initial states of the qubits
            n_samples=101,  # Number of samples
        )
        result = CustomSimulationResult(
            system=result.system,
            states=result.states,
            times=result.times,
            controls=result.controls,
            unitaries=result.unitaries,
        )
        return RunResult(raw_result=result)

    def batch_run(self, session: FakeSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
