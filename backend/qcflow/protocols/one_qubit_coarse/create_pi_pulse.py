from typing import ClassVar

from qcflow.cal_util import qid_to_label
from qcflow.manager.task import Data
from qcflow.protocols.base import (
    BaseTask,
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

    task_name: str = "CreatePIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "pi_amplitude": OutputParameter(unit="", description="PI pulse amplitude")
    }

    def __init__(
        self,
        pi_length=PI_DURATION,  # noqa: ANN001
        shots=CALIBRATION_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
    ) -> None:
        self.input_parameters = {
            "pi_length": pi_length,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
            "rabi_params": {},
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        label = qid_to_label(qid)
        input_param = {
            "pi_length": self.input_parameters["pi_length"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
            "qubit_frequency": exp.targets[label].frequency,
            "control_amplitude": exp.params.control_amplitude[label],
            "readout_frequency": exp.resonators[label].frequency,
            "readout_amplitude": exp.params.readout_amplitude[label],
            "rabi_frequency": exp.rabi_params[label].frequency,
            "rabi_amplitude": exp.rabi_params[label].amplitude,
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "pi_amplitude": Data(
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
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
