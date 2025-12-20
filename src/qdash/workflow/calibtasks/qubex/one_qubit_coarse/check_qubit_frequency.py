from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS
from qdash.datamodel.task import TaskTypes


class CheckQubitFrequency(QubexTask):
    """Task to check the qubit frequency."""

    name: str = "CheckQubitFrequency"
    task_type = TaskTypes.QUBIT
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "detuning_range": InputParameterModel(
            unit="GHz",
            value_type="np.linspace",
            value=(-0.01, 0.01, 21),
            description="Detuning range",
        ),
        "time_range": InputParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 101, 4),
            description="Time range",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "qubit_frequency": OutputParameterModel(unit="GHz", description="Qubit frequency"),
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
            detuning_range=self.input_parameters["detuning_range"].get_value(),
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        self.save_calibration(backend)
        return RunResult(raw_result=result)
