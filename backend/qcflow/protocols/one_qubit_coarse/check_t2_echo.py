from typing import ClassVar

import numpy as np
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
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckT2Echo(BaseTask):
    """Task to check the T2 echo time."""

    task_name: str = "CheckT2Echo"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "t2_echo": OutputParameter(unit="ns", description="T2 echo time"),
    }

    def __init__(
        self,
        time_range=None,  # noqa: ANN001
        shots=DEFAULT_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
    ) -> None:
        if time_range is None:
            time_range = np.logspace(np.log10(300), np.log10(100 * 1000), 51)
        self.input_parameters = {
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
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
            "t2_echo": Data(
                value=result.data[label].t2,
                unit=op["t2_echo"].unit,
                description=op["t2_echo"].description,
                execution_id=execution_id,
            ),
        }

        figures = [result.data[label].fit()["fig"]]
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.t2_experiment(
            labels,
            time_range=self.input_parameters["time_range"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
            save_image=False,
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
