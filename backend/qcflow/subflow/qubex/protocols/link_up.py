from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class LinkUp(BaseTask):
    task_name: str = "LinkUp"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.linkup()
        exp.save_defaults()
