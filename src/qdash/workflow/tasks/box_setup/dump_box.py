from typing import ClassVar

from qdash.workflow.tasks.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class DumpBox(BaseTask):
    """DumpBox class to dump the box information."""

    name: str = "DumpBox"
    task_type: str = "global"
    input_parameters: ClassVar[dict[str, InputParameter]] = {}
    output_parameters: ClassVar[dict[str, OutputParameter]] = {}

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, exp: Experiment, qid: str) -> RunResult:  # noqa: ARG002
        for _id in exp.box_ids:
            box_info = {}
            box_info[_id] = exp.tool.dump_box(_id)
        return RunResult(raw_result=box_info)
