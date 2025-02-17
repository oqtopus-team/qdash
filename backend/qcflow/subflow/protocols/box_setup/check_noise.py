from qcflow.subflow.protocols.base import BaseTask
from qcflow.subflow.task_manager import TaskManager
from qubex.experiment import Experiment


class CheckNoise(BaseTask):
    task_name: str = "CheckNoise"
    task_type: str = "global"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.check_noise()
        exp.save_defaults()
