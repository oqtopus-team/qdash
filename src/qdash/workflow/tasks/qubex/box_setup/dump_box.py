from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.engine.backend.qubex import QubexBackend
from qdash.workflow.tasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.tasks.qubex.base import QubexTask


class DumpBox(QubexTask):
    """DumpBox class to dump the box information."""

    name: str = "DumpBox"
    task_type: str = "global"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        pass

    def run(self, backend: QubexBackend, qid: str) -> RunResult:  # noqa: ARG002
        exp = self.get_experiment(backend)
        for _id in exp.box_ids:
            box_info = {}
            box_info[_id] = exp.tool.dump_box(_id)
        return RunResult(raw_result=box_info)
