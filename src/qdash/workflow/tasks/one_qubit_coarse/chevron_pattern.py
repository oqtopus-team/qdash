from typing import ClassVar

import numpy as np
from qdash.datamodel.task import InputParameterModel, OutputParameterModel
from qdash.workflow.calibration.util import qid_to_label
from qdash.workflow.tasks.base import (
    BaseTask,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qubex.experiment import Experiment


class ChevronPattern(BaseTask):
    """Task to check the chevron pattern."""

    name: str = "ChevronPattern"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameterModel]] = {}
    output_parameters: ClassVar[dict[str, OutputParameterModel]] = {}

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        pass

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        pass

    def run(self, exp: Experiment, qid: str) -> RunResult:
        labels = [qid_to_label(qid)]
        exp.chevron_pattern(
            targets=labels,
            detuning_range=np.linspace(-0.05, 0.05, 51),
            time_range=np.arange(0, 201, 4),
        )
        exp.calib_note.save()
        return RunResult(raw_result=None)

    def batch_run(self, exp: Experiment, qid: str) -> RunResult:
        """Batch run is not implemented."""
        raise NotImplementedError(
            f"Batch run is not implemented for {self.name} task. Use run method instead."
        )
