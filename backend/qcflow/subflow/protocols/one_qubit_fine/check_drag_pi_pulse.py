from typing import ClassVar

from qcflow.subflow.protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment


class CheckDRAGPIPulse(BaseTask):
    """Task to check the DRAG PI pulse."""

    task_name: str = "CheckDRAGPIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}

    def __init__(self) -> None:
        pass

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [convert_label(qid)]
        drag_pi_pulse = {qubit: exp.drag_pi_pulse[qubit] for qubit in labels}
        exp.repeat_sequence(
            sequence=drag_pi_pulse,
            repetitions=20,
        )
        exp.calib_note.save()
        return RunResult(raw_result=None)
