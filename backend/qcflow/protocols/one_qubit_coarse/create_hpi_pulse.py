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
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateHPIPulse(BaseTask):
    """Task to create the HPI pulse."""

    name: str = "CreateHPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "hpi_length": InputParameter(
            unit="ns", value_type="int", value=HPI_DURATION, description="HPI pulse length"
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
        "hpi_amplitude": OutputParameter(unit="", description="HPI pulse amplitude")
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "hpi_amplitude": DataModel(
                value=result.data[label].calib_value,
                unit=op["hpi_amplitude"].unit,
                description=op["hpi_amplitude"].description,
                execution_id=execution_id,
            ),
        }

        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.calibrate_hpi_pulse(
            targets=labels,
            n_rotations=1,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
