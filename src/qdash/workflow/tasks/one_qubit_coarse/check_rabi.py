from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibration.util import qid_to_label
from qdash.workflow.tasks.base import (
    BaseTask,
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
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "time_range": InputParameterModel(
            unit="ns",
            value_type="range",
            value=(0, 201, 4),
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "rabi_amplitude": OutputParameterModel(
            unit="a.u.", description="Rabi oscillation amplitude"
        ),
        "rabi_frequency": OutputParameterModel(
            unit="MHz", description="Rabi oscillation frequency"
        ),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Process the results of the task."""
        label = qid_to_label(qid)
        result = run_result.raw_result
        self.output_parameters["rabi_amplitude"].value = result.rabi_params[label].amplitude
        self.output_parameters["rabi_amplitude"].error = result.data[label].fit()["amplitude_err"]
        self.output_parameters["rabi_frequency"].value = (
            result.rabi_params[label].frequency * 1000
        )  # convert to MHz
        self.output_parameters["rabi_frequency"].error = (
            result.data[label].fit()["frequency_err"] * 1000
        )
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        raw_data = [result.data[label].data]
        r2 = result.rabi_params[label].r2
        if self.r2_is_lower_than_threshold(r2):
            raise ValueError(f"R^2 value of Rabi oscillation is too low: {r2}")
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

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
