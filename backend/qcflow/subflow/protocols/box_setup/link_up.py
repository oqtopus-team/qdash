from typing import ClassVar

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class LinkUp(BaseTask):
    """Task to link up the box."""

    task_name: str = "LinkUp"
    task_type: str = "global"
    output_parameters: ClassVar[list[str]] = []

    def __init__(self) -> None:
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager) -> None:
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager) -> None:
        exp.linkup()
        exp.calib_note.save(file_path=task_manager.calib_dir)
