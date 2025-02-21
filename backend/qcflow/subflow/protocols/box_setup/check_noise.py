from typing import ClassVar

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CheckNoise(BaseTask):
    """Task to check the noise."""

    task_name: str = "CheckNoise"
    task_type: str = "global"
    output_parameters: ClassVar[list[str]] = []

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, qid: str) -> None:
        exp.check_noise()
        exp.calib_note.save()
