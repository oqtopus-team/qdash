from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckNoise(BaseTask):
    task_name: str = "CheckNoise"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.check_noise()
        exp.save_defaults()
