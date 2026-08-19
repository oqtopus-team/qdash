from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckQubitFrequency(QubexTask):
    """Task to check the qubit frequency."""

    name: str = "CheckQubitFrequency"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "detuning_range": RunParameterSpec(
            unit="GHz",
            value_type="np.linspace",
            default=(-0.01, 0.01, 21),
            description="Detuning range",
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="range",
            default=(0, 101, 4),
            description="Time range",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qubit_frequency": OutputParameterSpec(unit="GHz", description="Qubit frequency"),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        self.output_parameters["qubit_frequency"].value = result[label]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        labels = [exp.get_qubit_label(int(qid))]
        result = exp.calibrate_control_frequency(
            labels,
            detuning_range=self.run_parameters["detuning_range"].get_value(),
            time_range=self.run_parameters["time_range"].get_value(),
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
