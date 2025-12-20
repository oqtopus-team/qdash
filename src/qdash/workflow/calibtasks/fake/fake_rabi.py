from collections import defaultdict
from typing import Any, ClassVar

import numpy as np
import numpy.typing as npt
import plotly.graph_objects as go
import qubex as qx
from qdash.datamodel.task import InputParameterModel, OutputParameterModel, TaskTypes
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.fake.base import FakeTask
from qdash.workflow.engine.backend.fake import FakeBackend
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS
from qubex.simulator import Control, QuantumSimulator, QuantumSystem, SimulationResult, Transmon


def downsample(
    data: npt.NDArray[Any],
    n_samples: int | None,
) -> npt.NDArray[Any]:
    """Downsample the data to a specified number of samples."""
    if n_samples is None:
        return data
    if len(data) <= n_samples:
        return data
    indices = np.linspace(0, len(data) - 1, n_samples).astype(int)
    return np.asarray(data[indices])


class CustomSimulationResult(SimulationResult):
    """Custom simulation result to handle Rabi parameters."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the custom simulation result."""
        super().__init__(**kwargs)

    def plot_population_dynamics(
        self, label: str | None = None, *, n_samples: int | None = None
    ) -> go.Figure:
        """Plot the population dynamics of the states.

        Parameters
        ----------
        label : Optional[str], optional
            The label of the qubit, by default
        n_samples : Optional[int], optional
            The number of samples to downsample the data, by default None

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
                    mode="lines+markers",
                    name=key,
                )
            )
        fig.update_layout(
            title="Population dynamics" if label is None else f"Population dynamics : {label}",
            xaxis_title="Time (ns)",
            yaxis_title="Population",
        )
        return fig


class FakeRabi(FakeTask):
    """Task to check the Fake Rabi oscillation."""

    name: str = "FakeRabi"
    task_type = TaskTypes.QUBIT
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

    def preprocess(self, backend: FakeBackend, qid: str) -> PreProcessResult:
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Process the results of the task."""
        result = run_result.raw_result

        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.plot_population_dynamics()]
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: FakeBackend, qid: str) -> RunResult:
        """Run the task."""
        label = self.get_label(qid)
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
