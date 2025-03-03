from typing import ClassVar

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
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, PI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreatePIPulse(BaseTask):
    """Task to create the pi pulse."""

    name: str = "CreatePIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "pi_length": InputParameter(
            unit="ns", value_type="int", value=PI_DURATION, description="PI pulse length"
        ),
        "shots": InputParameter(
            unit="",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for calibration",
        ),
        "interval": InputParameter(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for calibration",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "pi_amplitude": OutputParameter(unit="", description="PI pulse amplitude")
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "pi_amplitude": DataModel(
                value=result.data[label].calib_value,
                unit=op["pi_amplitude"].unit,
                description=op["pi_amplitude"].description,
                execution_id=execution_id,
            ),
        }
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.calibrate_pi_pulse(
            targets=labels,
            n_rotations=1,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
