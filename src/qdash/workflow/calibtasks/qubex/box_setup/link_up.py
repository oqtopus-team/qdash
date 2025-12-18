from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class LinkUp(QubexTask):
    """Task to link up the box."""

    name: str = "LinkUp"
    task_type: str = "global"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        pass

    def run(self, backend: QubexBackend, qid: str) -> RunResult:  # noqa: ARG002
        exp = self.get_experiment(backend)
        exp.linkup()
        self.save_calibration(backend)
        return RunResult(raw_result=None)
