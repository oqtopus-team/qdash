from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibration.util import qid_to_cr_pair
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class CheckZX90(BaseTask):
    """Task to check ZX90 pulse."""

    name: str = "CheckZX90"
    task_type: str = "coupling"
    timeout: int = 60 * 25  # 25 minutes
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {
        "repetitions": InputParameterModel(
            unit="a.u.",
            value_type="int",
            value=20,
            description="Number of repetitions for the PI pulse",
        )
    }
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        return PreProcessResult(input_parameters=self.input_parameters)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        control, target = qid_to_cr_pair(qid)
        result = run_result.raw_result
        figures = [
            result.data[control].plot(normalize=True, return_figure=True),
            result.data[target].plot(normalize=True, return_figure=True),
        ]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id), figures=figures
        )

    def run(self, exp: Experiment, qid: str) -> RunResult:
        cr_control, cr_target = qid_to_cr_pair(qid)
        zx90_pulse = exp.zx90(cr_control, cr_target)
        result = exp.repeat_sequence(
            sequence=zx90_pulse,
            repetitions=self.input_parameters["repetitions"].get_value(),
        )
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, exp: Experiment, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
