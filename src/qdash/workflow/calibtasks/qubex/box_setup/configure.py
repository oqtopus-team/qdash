from typing import ClassVar

from qdash.datamodel.task import ParameterModel, RunParameterModel
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class Configure(QubexTask):
    """Task to configure the box."""

    name: str = "Configure"
    task_type: str = "global"
    run_parameters: ClassVar[dict[str, RunParameterModel]] = {}
    output_parameters: ClassVar[dict[str, ParameterModel]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        exp.state_manager.load(
            chip_id=exp.chip_id, config_dir=exp.config_path, params_dir=exp.params_path
        )
        exp.state_manager.push(box_ids=exp.box_ids, confirm=False)
        self.save_calibration(backend)
        return RunResult(raw_result=None)
