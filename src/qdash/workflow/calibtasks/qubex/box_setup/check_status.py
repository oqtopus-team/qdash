from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel, TaskTypes
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckStatus(QubexTask):
    """Task to check the status of the experiment."""

    name: str = "CheckStatus"
    task_type = TaskTypes.GLOBAL
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:  # noqa: ARG002
        exp = self.get_experiment(backend)
        result = exp.check_status()
        self.save_calibration(backend)
        return RunResult(raw_result=result)
