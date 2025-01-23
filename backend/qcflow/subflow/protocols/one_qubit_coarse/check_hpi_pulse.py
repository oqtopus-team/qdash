from qcflow.subflow.manager import ExecutionManager
from qcflow.subflow.protocols.base import BaseTask
from qubex.experiment import Experiment


class CheckHPIPulse(BaseTask):
    task_name: str = "CheckHPIPulse"

    def __init__(self):
        pass

    def execute(self, exp: Experiment, execution_manager: ExecutionManager):
        exp.repeat_sequence(
            exp.hpi_pulse,
            repetitions=20,
        )
        exp.save_defaults()
