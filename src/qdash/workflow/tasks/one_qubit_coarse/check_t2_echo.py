from typing import ClassVar

import numpy as np
from qdash.datamodel.task import DataModel
from qdash.workflow.cal_util import qid_to_label
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


class CheckT2Echo(BaseTask):
    """Task to check the T2 echo time."""

    name: str = "CheckT2Echo"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "time_range": InputParameter(
            unit="ns",
            value_type="np.logspace",
            value=(np.log10(300), np.log10(100 * 1000), 51),
            description="Time range for T2 echo time",
        ),
        "shots": InputParameter(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for T2 echo time",
        ),
        "interval": InputParameter(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for T2 echo time",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "t2_echo": OutputParameter(unit="ns", description="T2 echo time"),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "t2_echo": DataModel(
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
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            save_image=False,
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
