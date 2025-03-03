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
from qubex.experiment.experiment import RABI_TIME_RANGE
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckRabi(BaseTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "time_range": InputParameter(
            unit="ns",
            value_type="ndarray",
            value="[0, 201, 4]",
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameter(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameter(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "rabi_amplitude": OutputParameter(unit="a.u.", description="Rabi oscillation amplitude"),
        "rabi_frequency": OutputParameter(unit="GHz", description="Rabi oscillation frequency"),
    }

    def __init__(
        self,
        time_range=RABI_TIME_RANGE,  # noqa: ANN001
        shots=DEFAULT_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
    ) -> None:
        super().__init__(time_range=time_range, shots=shots, interval=interval)
        self.input_parameters["time_range"].value = time_range
        self.input_parameters["shots"].value = shots
        self.input_parameters["interval"].value = interval

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        input_param = {
            "time_range": self.input_parameters["time_range"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "rabi_amplitude": DataModel(
                value=result.rabi_params[label].amplitude,
                unit=op["rabi_amplitude"].unit,
                description=op["rabi_amplitude"].description,
                execution_id=execution_id,
            ),
            "rabi_frequency": DataModel(
                value=result.rabi_params[label].frequency,
                unit=op["rabi_frequency"].unit,
                description=op["rabi_frequency"].description,
                execution_id=execution_id,
            ),
        }
        figures = [result.data[label].fit()["fig"]]
        raw_data = [result.data[label].data]
        return PostProcessResult(output_parameters=output_param, figures=figures, raw_data=raw_data)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = qid_to_label(qid)
        result = exp.obtain_rabi_params(
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
            targets=label,
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
