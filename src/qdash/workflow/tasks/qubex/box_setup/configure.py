from typing import ClassVar

from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.core.session.qubex import QubexSession
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)


class Configure(BaseTask):
    """Task to configure the box."""

    name: str = "Configure"
    task_type: str = "global"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, session: QubexSession, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, session: QubexSession, qid: str) -> RunResult:  # noqa: ARG002
        exp = session.get_session()
        exp.state_manager.load(
            chip_id=exp.chip_id, config_dir=exp.config_path, params_dir=exp.params_path
        )
        exp.state_manager.push(box_ids=exp.box_ids, confirm=False)
        exp.calib_note.save()
        return RunResult(raw_result=None)

    def batch_run(self, session: QubexSession, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
