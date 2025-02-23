from typing import ClassVar

from qcflow.protocols.base import (
    BaseTask,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class CheckNoise(BaseTask):
    """Task to check the noise."""

    name: str = "CheckNoise"
    task_type: str = "global"
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}

    def __init__(self) -> None:
        pass

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, exp: Experiment, qid: str) -> RunResult:  # noqa: ARG002
        exp.check_noise()
        exp.calib_note.save()
        return RunResult(raw_result=None)
