from typing import ClassVar

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import (
    PostProcessResult,
    RunResult,
)
from qdash.workflow.calibtasks.qubex.base import QubexTask
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckNoise(QubexTask):
    """Task to check the noise."""

    name: str = "CheckNoise"
    task_type: str = "global"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {}
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {}
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {}

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        return PostProcessResult(output_parameters={})

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        exp.check_noise()
        self.save_calibration(backend)
        return RunResult(raw_result=None)
