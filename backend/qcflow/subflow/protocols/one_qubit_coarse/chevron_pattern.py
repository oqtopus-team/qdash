from typing import Any, ClassVar

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qcflow.subflow.util import convert_label
from qubex.experiment import Experiment


class ChevronPattern(BaseTask):
    """Task to check the chevron pattern."""

    task_name: str = "ChevronPattern"
    task_type: str = "qubit"
    output_parameters: ClassVar[list[str]] = []

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        pass

    def _postprocess(
        self, exp: Experiment, task_manager: TaskManager, result: Any, qid: str
    ) -> None:
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        labels = [convert_label(qid)]
        exp.chevron_pattern(
            targets=labels,
            detuning_range=np.linspace(-0.05, 0.05, 51),
            time_range=np.arange(0, 201, 4),
        )
        exp.calib_note.save()
