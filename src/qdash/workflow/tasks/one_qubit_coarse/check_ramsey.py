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


class CheckRamsey(BaseTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRamsey"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "detuning": InputParameterModel(
            unit="GHz",
            value_type="float",
            value=0.001,
            description="Detuning for Ramsey oscillation",
        ),
        "time_range": InputParameterModel(
            unit="ns",
            value_type="np.arange",
            value=(0, 10001, 100),
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
        "ramsey_frequency": OutputParameterModel(
            unit="MHz", description="Ramsey oscillation frequency"
        ),
        "bare_frequency": OutputParameterModel(unit="GHz", description="Qubit bare frequency"),
        "t2_star": OutputParameterModel(unit="μs", description="T2* time"),
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:  # noqa: ARG002
        """Preprocess the task."""
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Process the results of the task."""
        label = qid_to_label(qid)
        result = run_result.raw_result.data[label]
        self.output_parameters["ramsey_frequency"].value = (
            result.fit()["f"] * 1000
        )  # convert to MHz
        self.output_parameters["ramsey_frequency"].error = result.fit()["f_err"] * 1000
        self.output_parameters["bare_frequency"].value = result.bare_freq
        self.output_parameters["t2_star"].value = result.t2 * 0.001  # convert to μs
        self.output_parameters["t2_star"].error = result.fit()["tau_err"] * 0.001  # convert to μs
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.fit()["fig"]]
        raw_data = [result.data]
        r2 = result.r2
        if self.r2_is_lower_than_threshold(r2):
            raise ValueError(f"R^2 value of Ramsey oscillation is too low: {r2}")
        return PostProcessResult(
            output_parameters=output_parameters, figures=figures, raw_data=raw_data
        )

    def run(self, exp: Experiment, qid: str) -> RunResult:
        """Run the task."""
        label = qid_to_label(qid)
        result = exp.ramsey_experiment(
            time_range=self.input_parameters["time_range"].get_value(),
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
            detuning=self.input_parameters["detuning"].get_value(),
            spectator_state="0",
            targets=label,
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, exp: Experiment, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
