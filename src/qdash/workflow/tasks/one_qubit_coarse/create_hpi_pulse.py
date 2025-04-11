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
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS, HPI_DURATION
from qubex.measurement.measurement import DEFAULT_INTERVAL


class CreateHPIPulse(BaseTask):
    """Task to create the HPI pulse."""

    name: str = "CreateHPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "hpi_length": InputParameterModel(
            unit="ns", value_type="int", value=HPI_DURATION, description="HPI pulse length"
        ),
        "shots": InputParameterModel(
            unit="",
            value_type="int",
            value=CALIBRATION_SHOTS,
            description="Number of shots for calibration",
        ),
        "interval": InputParameterModel(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for calibration",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {
        "hpi_amplitude": OutputParameterModel(unit="", description="HPI pulse amplitude")
    }

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        label = qid_to_label(qid)
        result = run_result.raw_result
        self.output_parameters["hpi_amplitude"].value = result.data[label].calib_value
        output_parameters = self.attach_execution_id(execution_id)
        figures = [result.data[label].fit()["fig"]]
        r2 = result.data[label].r2
        if self.r2_is_lower_than_threshold(r2):
            raise ValueError(f"R^2 value of CreateHPIPulse is below threshold: {r2}")
        return PostProcessResult(output_parameters=output_parameters, figures=figures)

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        result = exp.calibrate_hpi_pulse(
            targets=labels,
            n_rotations=1,
            shots=self.input_parameters["shots"].get_value(),
            interval=self.input_parameters["interval"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, exp: Experiment, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
