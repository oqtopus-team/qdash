from typing import ClassVar

from qcflow.cal_util import qid_to_label
from qcflow.protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class CheckDRAGHPIPulse(BaseTask):
    """Task to check the DRAG HPI pulse."""

    name: str = "CheckDRAGHPIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}

    def __init__(self) -> None:
        pass

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
