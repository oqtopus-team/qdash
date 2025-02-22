from typing import ClassVar

import numpy as np
from qcflow.manager.task import Data
from qcflow.qubex_protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckEffectiveQubitFrequency(BaseTask):
    """Task to check the effective qubit frequency."""

    task_name: str = "CheckEffectiveQubitFrequency"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "effective_qubit_frequency": OutputParameter(
            unit="GHz", description="Effective qubit frequency"
        ),
        "effective_qubit_frequency_0": OutputParameter(
            unit="GHz", description="Effective qubit frequency for qubit 0"
        ),
        "effective_qubit_frequency_1": OutputParameter(
            unit="GHz", description="Effective qubit frequency for qubit 1"
        ),
    }

    def __init__(
        self,
        detuning=0.001,  # noqa: ANN001
        time_range=None,  # noqa: ANN001
        shots=DEFAULT_SHOTS,  # noqa: ANN001
        interval=DEFAULT_INTERVAL,  # noqa: ANN001
    ) -> None:
        if time_range is None:
            time_range = np.arange(0, 20001, 100)

        self.input_parameters = {
            "detuning": detuning,
            "time_range": time_range,
            "shots": shots,
            "interval": interval,
        }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        input_param = {
            "detuning": self.input_parameters["detuning"],
            "time_range": self.input_parameters["time_range"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = convert_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "effective_qubit_frequency": Data(
                value=result["effective_freq"][label],
                unit=op["effective_qubit_frequency"].unit,
                description=op["effective_qubit_frequency"].description,
                execution_id=execution_id,
            ),
            "effective_qubit_frequency_0": Data(
                value=result["result_0"].data[label].bare_freq,
                unit=op["effective_qubit_frequency_0"].unit,
                description=op["effective_qubit_frequency_0"].description,
                execution_id=execution_id,
            ),
            "effective_qubit_frequency_1": Data(
                value=result["result_1"].data[label].bare_freq,
                unit=op["effective_qubit_frequency_1"].unit,
                description=op["effective_qubit_frequency_1"].description,
                execution_id=execution_id,
            ),
        }

        figures = [
            result["result_0"].data[label].fit()["fig"],
            result["result_1"].data[label].fit()["fig"],
        ]
        return PostProcessResult(output_parameters=output_param, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        label = convert_label(qid)
        result = exp.obtain_effective_control_frequency(
            targets=[label],
            time_range=self.input_parameters["time_range"],
            detuning=self.input_parameters["detuning"],
            shots=self.input_parameters["shots"],
            interval=self.input_parameters["interval"],
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
