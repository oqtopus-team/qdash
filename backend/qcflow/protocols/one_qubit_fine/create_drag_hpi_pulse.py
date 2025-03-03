from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import plotly.graph_objs as go
from datamodel.task import DataModel
from qcflow.cal_util import qid_to_label
from qcflow.protocols.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateDRAGHPIPulse(BaseTask):
    """Task to create the DRAG HPI pulse."""

    name: str = "CreateDRAGHPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "hpi_length": InputParameter(
            unit="ns",
            value_type="int",
            value=HPI_DURATION,
            description="HPI pulse length",
        ),
        "shots": InputParameter(
            unit="a.u.",
            value_type="int",
            value=CALIBRATION_SHOTS,
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
        "drag_hpi_beta": OutputParameter(unit="", description="DRAG HPI pulse beta"),
        "drag_hpi_amplitude": OutputParameter(unit="", description="DRAG HPI pulse amplitude"),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "drag_hpi_beta": DataModel(
                value=result["beta"][label],
                unit=op["drag_hpi_beta"].unit,
                description=op["drag_hpi_beta"].description,
                execution_id=execution_id,
            ),
            "drag_hpi_amplitude": DataModel(
                value=result["amplitude"][label],
                unit=op["drag_hpi_amplitude"].unit,
                description=op["drag_hpi_amplitude"].description,
                execution_id=execution_id,
            ),
        }
        figures: list[go.Figure] = []
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.calibrate_drag_hpi_pulse(
            targets=labels,
            n_rotations=4,
            n_turns=1,
            n_iterations=2,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
