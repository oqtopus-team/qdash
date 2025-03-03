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
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class CheckEffectiveQubitFrequency(BaseTask):
    """Task to check the effective qubit frequency."""

    name: str = "CheckEffectiveQubitFrequency"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "detuning": InputParameter(
            unit="GHz", value_type="float", value=0.001, description="Detuning"
        ),
        "time_range": InputParameter(
            unit="ns",
            value_type="np.arange",
            value=(0, 20001, 100),
            description="Time range for effective qubit frequency",
        ),
        "shots": InputParameter(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for effective qubit frequency",
        ),
        "interval": InputParameter(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for effective qubit frequency",
        ),
    }
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

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        op = self.output_parameters
        output_param = {
            "effective_qubit_frequency": DataModel(
                value=result["effective_freq"][label],
                unit=op["effective_qubit_frequency"].unit,
                description=op["effective_qubit_frequency"].description,
                execution_id=execution_id,
            ),
            "effective_qubit_frequency_0": DataModel(
                value=result["result_0"].data[label].bare_freq,
                unit=op["effective_qubit_frequency_0"].unit,
                description=op["effective_qubit_frequency_0"].description,
                execution_id=execution_id,
            ),
            "effective_qubit_frequency_1": DataModel(
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
        label = qid_to_label(qid)
        result = exp.obtain_effective_control_frequency(
            targets=[label],
            time_range=self.input_parameters["time_range"].get_value(),
            detuning=self.input_parameters["detuning"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
