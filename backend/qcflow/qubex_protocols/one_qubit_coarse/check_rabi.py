from typing import ClassVar

from qcflow.qubex_protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qcflow.subflow.task_manager import Data
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment
from qubex.experiment.experiment import RABI_TIME_RANGE
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckRabi(BaseTask):
    """Task to check the Rabi oscillation."""

    task_name: str = "CheckRabi"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "rabi_amplitude": OutputParameter(unit="", description="Rabi oscillation amplitude"),
        "rabi_frequency": OutputParameter(unit="GHz", description="Rabi oscillation frequency"),
    }

    def __init__(
        self,
        time_range=RABI_TIME_RANGE,  # noqa: ANN001
        shots=DEFAULT_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
    ) -> None:
        self.input_parameters: dict = {
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
            "qubit_frequency": {},
            "control_amplitude": {},
            "readout_frequency": {},
            "readout_amplitude": {},
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        label = convert_label(qid)
        input_param = {
            "time_range": self.input_parameters["time_range"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
            "qubit_frequency": exp.targets[label].frequency,
            "control_amplitude": exp.params.control_amplitude[label],
            "readout_frequency": exp.resonators[label].frequency,
            "readout_amplitude": exp.params.readout_amplitude[label],
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = convert_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "rabi_amplitude": Data(
                value=result.rabi_params[label].amplitude,
                unit=op["rabi_amplitude"].unit,
                description=op["rabi_amplitude"].description,
                execution_id=execution_id,
            ),
            "rabi_frequency": Data(
                value=result.rabi_params[label].frequency,
                unit=op["rabi_frequency"].unit,
                description=op["rabi_frequency"].description,
                execution_id=execution_id,
            ),
        }
        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = convert_label(qid)
        result = exp.obtain_rabi_params(
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
            targets=label,
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
