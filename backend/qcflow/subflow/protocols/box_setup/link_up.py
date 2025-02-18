from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class LinkUp(BaseTask):
    task_name: str = "LinkUp"
    task_type: str = "global"

    def __init__(self):
        pass

    def _preprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def _postprocess(self, exp: Experiment, task_manager: TaskManager):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.linkup()
        exp.save_defaults()
