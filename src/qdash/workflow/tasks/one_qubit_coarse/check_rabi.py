from typing import ClassVar

from qdash.datamodel.task import DataModel
from qdash.workflow.calibration.util import qid_to_label
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


class CheckRabi(BaseTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "time_range": InputParameter(
            unit="ns",
            value_type="range",
            value=(0, 201, 4),
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameter(
            unit="a.u.",
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

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Process the results of the task."""
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
        """Run the task."""
        label = qid_to_label(qid)
        result = exp.obtain_rabi_params(
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            targets=label,
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)
