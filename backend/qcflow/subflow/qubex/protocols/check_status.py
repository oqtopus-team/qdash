from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckStatus(BaseTask):
    task_name: str = "CheckStatus"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager):
        exp.check_status()
        exp.save_defaults()
