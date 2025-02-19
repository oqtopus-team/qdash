from typing import Any

from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CheckStatus(BaseTask):
    task_name: str = "CheckStatus"
    task_type: str = "qubit"

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager, result: Any):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.check_status()
        exp.calib_note.save(file_path=task_manager.calib_dir)
