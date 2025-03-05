from typing import ClassVar

from qubex.experiment import Experiment

from qdash.workflow.cal_util import qid_to_label
from qdash.workflow.tasks.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckDRAGHPIPulse(BaseTask):
    """Task to check the DRAG HPI pulse."""

    name: str = "CheckDRAGHPIPulse"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {}
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        drag_hpi_pulse = {qubit: exp.drag_hpi_pulse[qubit] for qubit in labels}
        exp.repeat_sequence(
            sequence=drag_hpi_pulse,
            repetitions=20,
        )
        exp.calib_note.save()
        return RunResult(raw_result=None)
