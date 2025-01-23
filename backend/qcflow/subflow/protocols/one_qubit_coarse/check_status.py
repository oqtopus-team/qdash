from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckStatus(BaseTask):
    task_name: str = "CheckStatus"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        exp.check_status()
        exp.save_defaults()
