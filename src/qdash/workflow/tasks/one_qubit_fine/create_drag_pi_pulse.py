from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibration.util import qid_to_label
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGPIPulse(BaseTask):
    """Task to create the DRAG pi pulse."""

    name: str = "CreateDRAGPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "pi_length": InputParameterModel(
            unit="ns",
            value_type="int",
            value=PI_DURATION,
            description="PI pulse length",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
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
        "drag_pi_beta": OutputParameterModel(unit="", description="DRAG PI pulse beta"),
        "drag_pi_amplitude": OutputParameterModel(unit="", description="DRAG PI pulse amplitude"),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        self.output_parameters["drag_pi_beta"].value = result["beta"][label]
        self.output_parameters["drag_pi_amplitude"].value = result["amplitude"][label]["amplitude"]
        output_parameters = self.attach_execution_id(execution_id)
        figures: list[go.Figure] = [result["amplitude"][label]["fig"]]
        r2 = result["amplitude"][label]["r2"]
        if self.r2_is_lower_than_threshold(r2):
            raise ValueError(f"R^2 value of CreateDRAGPIPulse is below threshold: {r2}")
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.calibrate_drag_pi_pulse(
            targets=labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
