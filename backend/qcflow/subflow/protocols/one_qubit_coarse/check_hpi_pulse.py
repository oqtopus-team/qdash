from typing import Any, ClassVar

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CheckHPIPulse(BaseTask):
    """Task to check the HPI pulse."""

    task_name: str = "CheckHPIPulse"
    task_type: str = "qubit"
    output_parameters: ClassVar[list[str]] = []

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any) -> None:
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        exp.repeat_sequence(
            exp.hpi_pulse,
            repetitions=20,
        )
        exp.calib_note.save(file_path=task_manager.calib_dir)
