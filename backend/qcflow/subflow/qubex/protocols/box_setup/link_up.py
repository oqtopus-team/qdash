from qcflow.subflow.qubex.manager import ExecutionManager
from qcflow.subflow.qubex.protocols.base import BaseTask
from qubex.experiment import Experiment


class LinkUp(BaseTask):
    task_name: str = "LinkUp"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        exp.linkup()
        exp.save_defaults()
