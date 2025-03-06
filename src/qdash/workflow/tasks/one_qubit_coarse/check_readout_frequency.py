from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qdash.datamodel.task import DataModel
from qdash.workflow.calibration.util import qid_to_label
from qdash.workflow.tasks.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckReadoutFrequency(BaseTask):
    """Task to check the readout frequency."""

    name: str = "CheckReadoutFrequency"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "detuning_range": InputParameter(
            unit="GHz",
            value_type="np.linspace",
            value=(-0.01, 0.01, 21),
            description="Detuning range",
        ),
        "time_range": InputParameter(
            unit="ns",
            value_type="range",
            value=(0, 101, 4),
            description="Time range",
        ),
        "shots": InputParameter(
            unit="a.u.",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots",
        ),
        "interval": InputParameter(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "readout_frequency": OutputParameter(unit="GHz", description="Readout frequency"),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "readout_frequency": DataModel(
                value=result[label],
                unit=op["readout_frequency"].unit,
                description=op["readout_frequency"].description,
                execution_id=execution_id,
            ),
        }
        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.calibrate_readout_frequency(
            labels,
            detuning_range=self.input_parameters["detuning_range"].get_value(),
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
