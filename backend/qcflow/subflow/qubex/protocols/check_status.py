from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment
from subflow.qubex.manager import TaskManager


class CheckStatus(BaseTask):
    task_name = "CheckStatus"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, task_manager: TaskManager, task_name: str):
        exp.check_status()
        exp.save_defaults()
