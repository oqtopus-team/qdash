from typing import Any, ClassVar

import numpy as np
from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class ChevronPattern(BaseTask):
    """Task to check the chevron pattern."""

    task_name: str = "ChevronPattern"
    task_type: str = "qubit"
    output_parameters: ClassVar[list[str]] = []

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any) -> None:
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        exp.chevron_pattern(
            exp.qubit_labels,
            detuning_range=np.linspace(-0.05, 0.05, 51),
            time_range=np.arange(0, 201, 4),
        )
        exp.calib_note.save(file_path=task_manager.calib_dir)
