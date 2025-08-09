from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class CheckStatus(BaseTask):
    """Task to check the status of the experiment."""

    name: str = "CheckStatus"
    backend: str = "qubex"
    task_type: str = "global"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        pass

    def postprocess(
        self, session: QubexSession, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        pass

    def run(self, session: QubexSession, qid: str) -> RunResult:  # noqa: ARG002
        exp = session.get_session()
        result = exp.check_status()
        exp.calib_note.save()
        return RunResult(raw_result=result)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(f"Batch run is not implemented for {self.name} task. Use run method instead.")
